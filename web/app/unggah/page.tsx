'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react'
import {
  IconAlert,
  IconArrowLeft,
  IconCheck,
  IconClose,
  IconExternal,
  IconFile,
  IconImage,
  IconPerson,
  IconShield,
  IconSparkle,
  IconUpload,
} from '../../components/icons'
import { useReportAuth } from '../../components/shell'
import { ErrorState, LoadingState, OfflineState, SignedOutState } from '../../components/states'
import {
  addClient,
  ApiError,
  loadIssueLabels,
  loadSession,
  loadTaxPresets,
  OFFLINE_MESSAGE,
  reviewUrl,
  SESSION_CHANGED_MESSAGE,
} from '../../lib/api'
import { useMainAppOrigin } from '../../lib/hooks'
import { canUpload } from '../../lib/status'
import type { Batch, BatchItem, CreatedClient, IssueLabels, Session, TaxPreset, TaxSelection } from '../../lib/types'
import {
  createBatch,
  FILE_ACCEPT,
  fileManifest,
  formatSize,
  getBatch,
  isStillWorking,
  matchManifest,
  MAX_FILES,
  newIdempotencyKey,
  pickFile,
  POLL_MS,
  PROBLEM_NOTES,
  progressOf,
  STEP_LABELS,
  uploadBatchItem,
  type FileProgress,
  type ManifestEntry,
  type PickedFile,
  type SendState,
  type StepState,
} from '../../lib/upload'

type SessionView =
  | { kind: 'loading' }
  | { kind: 'signed-out' }
  | { kind: 'offline' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; session: Session }

type PresetView = { kind: 'loading' } | { kind: 'ready'; presets: TaxPreset[] } | { kind: 'failed' }

/** idle: form open. preparing: checking files and creating the upload. sending: files on their way. tracking: polling. */
type Phase = 'idle' | 'preparing' | 'sending' | 'tracking'

interface Submitted {
  files: PickedFile[]
  manifests: ManifestEntry[]
}

const NO_LABELS: IssueLabels = {}
const MAX_POLL_FAILURES = 5
const EMPTY_CLIENT = { name: '', city: '', sector: '', npwp: '', code: '' }

const STEP_STATE_TEXT: Record<StepState, string> = {
  todo: 'belum',
  active: 'sedang berjalan',
  done: 'selesai',
  warn: 'perlu dicek',
  failed: 'gagal',
}

function fileSignature(file: File): string {
  return `${file.name}\u0000${file.size}\u0000${file.lastModified}`
}

export default function UploadPage() {
  const reportAuth = useReportAuth()
  const origin = useMainAppOrigin()

  const [sessionView, setSessionView] = useState<SessionView>({ kind: 'loading' })
  const [presetView, setPresetView] = useState<PresetView>({ kind: 'loading' })
  const [labels, setLabels] = useState<IssueLabels>(NO_LABELS)

  const [clientId, setClientId] = useState('')
  const [presetId, setPresetId] = useState('')
  const [hasNpwp, setHasNpwp] = useState(true)
  const [files, setFiles] = useState<PickedFile[]>([])
  const [dragging, setDragging] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [clientDialog, setClientDialog] = useState(false)
  const [clientNote, setClientNote] = useState<string | null>(null)

  const [phase, setPhase] = useState<Phase>('idle')
  const [batch, setBatch] = useState<Batch | null>(null)
  const [sendStates, setSendStates] = useState<Record<number, SendState>>({})
  const [notice, setNotice] = useState<string | null>(null)
  const [pollFailures, setPollFailures] = useState(0)

  // The same key is reused when a failed attempt is retried unchanged, so the server
  // returns the upload it may already have created. Any change to the choices drops it.
  const idempotencyKey = useRef<string | null>(null)
  const submitted = useRef<Submitted>({ files: [], manifests: [] })
  const contextRun = useRef<AbortController | null>(null)
  const uploadRun = useRef<AbortController | null>(null)
  const needsContext = useRef(true)

  const loadContext = useCallback(async () => {
    contextRun.current?.abort()
    const controller = new AbortController()
    contextRun.current = controller
    setSessionView((current) => (current.kind === 'ready' ? current : { kind: 'loading' }))
    let session: Session
    try {
      session = await loadSession(controller.signal)
    } catch (error) {
      if (controller.signal.aborted) return
      const failure = asApiError(error)
      if (failure.kind === 'unauthenticated') {
        setSessionView({ kind: 'signed-out' })
        reportAuth({ kind: 'signed-out' })
      } else {
        setSessionView(failure.kind === 'offline' ? { kind: 'offline' } : { kind: 'error', message: failure.message })
      }
      return
    }
    if (controller.signal.aborted) return
    setSessionView({ kind: 'ready', session })
    reportAuth({ kind: 'signed-in', name: session.name, role: session.role })
    // The uploader names the client on purpose; only a single-client account is filled in.
    setClientId((current) =>
      session.clients.some((client) => client.id === current)
        ? current
        : session.clients.length === 1 ? session.clients[0].id : '',
    )
    void loadIssueLabels().then((loaded) => {
      if (!controller.signal.aborted) setLabels(loaded)
    })
    setPresetView((current) => (current.kind === 'ready' ? current : { kind: 'loading' }))
    try {
      const presets = await loadTaxPresets(controller.signal)
      if (!controller.signal.aborted) setPresetView({ kind: 'ready', presets })
    } catch {
      if (!controller.signal.aborted) setPresetView({ kind: 'failed' })
    }
  }, [reportAuth])

  useEffect(() => {
    needsContext.current = sessionView.kind !== 'ready'
  }, [sessionView.kind])

  useEffect(() => {
    void loadContext()
    // Coming back after logging in on the main app loads the page again by itself.
    const retryIfVisible = () => {
      if (document.visibilityState === 'visible' && needsContext.current) void loadContext()
    }
    const retryIfRestored = (event: PageTransitionEvent) => {
      if (event.persisted && needsContext.current) void loadContext()
    }
    document.addEventListener('visibilitychange', retryIfVisible)
    window.addEventListener('pageshow', retryIfRestored)
    return () => {
      document.removeEventListener('visibilitychange', retryIfVisible)
      window.removeEventListener('pageshow', retryIfRestored)
      contextRun.current?.abort()
      uploadRun.current?.abort()
    }
  }, [loadContext])

  // A file dropped next to the drop zone must not make the browser open it instead.
  useEffect(() => {
    const keepPage = (event: globalThis.DragEvent) => {
      if (event.dataTransfer?.types.includes('Files')) event.preventDefault()
    }
    window.addEventListener('dragover', keepPage)
    window.addEventListener('drop', keepPage)
    return () => {
      window.removeEventListener('dragover', keepPage)
      window.removeEventListener('drop', keepPage)
    }
  }, [])

  // Poll while any invoice is still queued or being read (1.5 s, like batches.js).
  useEffect(() => {
    if (phase !== 'tracking' || !batch || !isStillWorking(batch) || pollFailures >= MAX_POLL_FAILURES) return
    const controller = new AbortController()
    const delay = pollFailures === 0 ? POLL_MS : Math.min(POLL_MS * 2 ** pollFailures, 15_000)
    const timer = window.setTimeout(async () => {
      try {
        const next = await getBatch(batch.id, controller.signal)
        if (controller.signal.aborted) return
        setPollFailures(0)
        setBatch(next)
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.kind === 'unauthenticated') {
          setSessionView({ kind: 'signed-out' })
          reportAuth({ kind: 'signed-out' })
          return
        }
        setPollFailures((count) => count + 1)
      }
    }, delay)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [phase, batch, pollFailures, reportAuth])

  const session = sessionView.kind === 'ready' ? sessionView.session : null
  const presets = presetView.kind === 'ready' ? presetView.presets : []
  const preset = presets.find((item) => item.id === presetId) ?? null
  const locked = phase !== 'idle'
  const overLimit = files.length > MAX_FILES
  const withProblems = files.filter((file) => file.problem !== null).length

  const choicesChanged = () => {
    idempotencyKey.current = null
    setFormError(null)
  }

  /** The server gives the new client to its creator, so a fresh session lists it in the server's own order. */
  const clientCreated = async (created: CreatedClient) => {
    const fresh = await loadSession(new AbortController().signal).catch(() => null)
    setSessionView((current) => {
      if (current.kind !== 'ready') return current
      const next = fresh ?? current.session
      return next.clients.some((client) => client.id === created.client.id)
        ? { kind: 'ready', session: next }
        : { kind: 'ready', session: { ...next, clients: [...next.clients, created.client] } }
    })
    setClientId(created.client.id)
    choicesChanged()
    const { name, code } = created.client
    setClientNote(`Klien ${name} terdaftar dengan kode ${code}. Akses: ${created.members.join(', ')}.`)
  }

  const addFiles = (list: FileList | null) => {
    if (locked || !list || list.length === 0) return
    const incoming = Array.from(list)
    setFiles((current) => {
      const seen = new Set(current.map((picked) => fileSignature(picked.file)))
      const fresh = incoming.filter((file) => !seen.has(fileSignature(file))).map(pickFile)
      return fresh.length ? [...current, ...fresh] : current
    })
    choicesChanged()
  }

  const removeFile = (key: string) => {
    if (locked) return
    setFiles((current) => current.filter((picked) => picked.key !== key))
    choicesChanged()
  }

  const onDragOver = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    if (locked) return
    event.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }
  const onDragLeave = (event: DragEvent<HTMLElement>) => {
    const next = event.relatedTarget
    if (next instanceof Node && event.currentTarget.contains(next)) return
    setDragging(false)
  }
  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragging(false)
    addFiles(event.dataTransfer.files)
  }

  const signOut = () => {
    setSessionView({ kind: 'signed-out' })
    reportAuth({ kind: 'signed-out' })
  }

  /** Error after the upload exists: keep the results on screen and explain what happened. */
  const explain = (error: unknown): string => {
    const failure = asApiError(error)
    if (failure.code === 'CSRF_REJECTED' || failure.code === 'ORIGIN_REJECTED') return SESSION_CHANGED_MESSAGE
    if (failure.kind === 'offline') return `${OFFLINE_MESSAGE} Coba lagi sebentar lagi.`
    return failure.message
  }

  /** Sends every pending file that matches a selected one, then reads the durable result. */
  const sendPending = async (start: Batch, csrf: string, controller: AbortController) => {
    const { files: picked, manifests } = submitted.current
    let current = start
    let matched = 0
    for (const item of start.items.filter((entry) => entry.status === 'PENDING')) {
      const index = matchManifest(item, manifests)
      if (index < 0) continue
      matched += 1
      setSendStates((states) => ({ ...states, [item.position]: 'sending' }))
      try {
        current = await uploadBatchItem(csrf, current.id, item.position, picked[index].file, controller.signal)
        if (controller.signal.aborted) return
        setBatch(current)
        setSendStates((states) => withoutPosition(states, item.position))
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404)) throw error
        // A lost response is ambiguous. Continue with the other files and read the durable result next.
        setSendStates((states) => ({ ...states, [item.position]: 'unconfirmed' }))
      }
    }
    current = await getBatch(current.id, controller.signal)
    if (controller.signal.aborted) return
    const stillPending = new Set(current.items.filter((item) => item.status === 'PENDING').map((item) => item.position))
    setBatch(current)
    setSendStates((states) => keepPositions(states, stillPending))
    setPollFailures(0)
    setPhase('tracking')
    if (current.counts.pending > 0) {
      setNotice(
        matched === 0
          ? 'File pilihan Anda tidak cocok dengan unggahan ini. Mulai unggahan baru.'
          : 'Sebagian file belum terkirim. File yang sudah diterima tetap tersimpan.',
      )
    }
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (locked || !session) return
    const problem = !clientId
      ? 'Pilih klien dulu.'
      : !preset
        ? 'Pilih jenis pajak dulu.'
        : files.length === 0
          ? 'Pilih minimal satu file invoice.'
          : overLimit
            ? `Maksimal ${MAX_FILES} file sekali unggah. Hapus ${files.length - MAX_FILES} file dulu.`
            : null
    if (problem || !preset) {
      setFormError(problem)
      return
    }
    const selection: TaxSelection = {
      pph: preset.pph,
      ppn: preset.ppn,
      recipient_has_npwp: hasNpwp,
      faktur_number: null,
    }
    const picked = files.slice()
    const controller = new AbortController()
    uploadRun.current?.abort()
    uploadRun.current = controller
    setFormError(null)
    setNotice(null)
    setPhase('preparing')
    let created: Batch | null = null
    try {
      const manifests: ManifestEntry[] = []
      for (const file of picked) manifests.push(await fileManifest(file))
      if (controller.signal.aborted) return
      const key = idempotencyKey.current ?? newIdempotencyKey()
      idempotencyKey.current = key
      created = await createBatch(session.csrf, key, clientId, manifests, selection, controller.signal)
      if (controller.signal.aborted) return
      submitted.current = { files: picked, manifests }
      setSendStates({})
      setBatch(created)
      setPhase('sending')
      await sendPending(created, session.csrf, controller)
    } catch (error) {
      if (controller.signal.aborted) return
      setSendStates(markUnconfirmed)
      if (error instanceof ApiError && error.kind === 'unauthenticated') {
        signOut()
        setPhase(created ? 'tracking' : 'idle')
        return
      }
      if (error instanceof ApiError && error.code === 'IDEMPOTENCY_CONFLICT') idempotencyKey.current = null
      if (!(error instanceof ApiError)) console.error(error)
      if (created) {
        setNotice(explain(error))
        setPhase('tracking')
      } else {
        setFormError(explain(error))
        setPhase('idle')
      }
    }
  }

  const retryPending = async () => {
    if (!batch || !session || phase !== 'tracking') return
    const controller = new AbortController()
    uploadRun.current?.abort()
    uploadRun.current = controller
    setNotice(null)
    setPhase('sending')
    try {
      await sendPending(batch, session.csrf, controller)
    } catch (error) {
      if (controller.signal.aborted) return
      setSendStates(markUnconfirmed)
      if (error instanceof ApiError && error.kind === 'unauthenticated') signOut()
      else setNotice(explain(error))
      setPhase('tracking')
    }
  }

  const startOver = () => {
    uploadRun.current?.abort()
    uploadRun.current = null
    idempotencyKey.current = null
    submitted.current = { files: [], manifests: [] }
    setBatch(null)
    setFiles([])
    setSendStates({})
    setNotice(null)
    setFormError(null)
    setClientNote(null)
    setPollFailures(0)
    setPhase('idle')
  }

  const progress = useMemo(
    () =>
      batch
        ? batch.items.map((item) => ({
            item,
            progress: progressOf(item, sendStates[item.position], phase === 'sending', labels),
          }))
        : [],
    [batch, sendStates, phase, labels],
  )
  const summary = useMemo(() => summarize(progress.map((entry) => entry.progress)), [progress])

  const reload = () => void loadContext()
  const canRetry =
    phase === 'tracking' &&
    batch !== null &&
    batch.can_upload &&
    batch.counts.pending > 0 &&
    submitted.current.files.length > 0

  return (
    <main id="konten" className="page">
      <div className="page-head">
        <div className="page-heading">
          <h1>Unggah invoice</h1>
          <p className="lead">Kirim sampai 5 invoice sekaligus. Progres tiap file tampil di halaman ini.</p>
        </div>
        <div className="page-actions">
          <Link className="button button-secondary" href="/">
            <IconArrowLeft size={18} />
            Kembali ke dashboard
          </Link>
        </div>
      </div>

      {sessionView.kind === 'loading' ? <LoadingState title="Menyiapkan halaman unggah…" /> : null}
      {sessionView.kind === 'signed-out' ? <SignedOutState onRetry={reload} /> : null}
      {sessionView.kind === 'offline' ? <OfflineState onRetry={reload} autoRetry={false} /> : null}
      {sessionView.kind === 'error' ? (
        <ErrorState title="Halaman unggah belum bisa dibuka." message={sessionView.message} onRetry={reload} />
      ) : null}

      {session && !canUpload(session.role) ? (
        <ErrorState
          title="Akun Anda belum bisa mengunggah invoice."
          message="Unggah invoice hanya untuk PIC klien. Finance dan Manajer Keuangan memeriksa dari menu Persetujuan."
        />
      ) : null}
      {session && canUpload(session.role) && session.clients.length === 0 ? (
        <ErrorState
          title="Akun Anda belum terhubung ke klien."
          message="Daftarkan klien pertama Anda di sini. Untuk klien yang sudah ada, minta admin AMIGA menghubungkan akun Anda."
        >
          <div className="state-actions">
            <button
              type="button"
              className="button button-primary"
              aria-haspopup="dialog"
              onClick={() => setClientDialog(true)}
            >
              + Klien baru
            </button>
          </div>
        </ErrorState>
      ) : null}

      {session && canUpload(session.role) && session.clients.length > 0 ? (
        <div className="upload-layout">
          <div className="upload-main">
            {batch ? (
              <section className="card results" aria-labelledby="results-title">
                <div className="results-head">
                  <div>
                    <h2 id="results-title" className="section-title">
                      Progres unggahan
                    </h2>
                    <p className="section-meta">{summary || 'Menyiapkan…'}</p>
                  </div>
                  <div className="results-actions">
                    {canRetry ? (
                      <button type="button" className="button button-secondary" onClick={() => void retryPending()}>
                        Kirim ulang yang belum terkirim
                      </button>
                    ) : null}
                    {phase === 'tracking' ? (
                      <button type="button" className="button button-primary" onClick={startOver}>
                        <IconUpload size={18} />
                        Unggah invoice lain
                      </button>
                    ) : null}
                  </div>
                </div>

                <p className="sr-only" aria-live="polite">
                  {summary}
                </p>

                {notice ? (
                  <div className="banner" role="alert">
                    <IconAlert size={20} />
                    <p>{notice}</p>
                  </div>
                ) : null}
                {pollFailures >= MAX_POLL_FAILURES ? (
                  <div className="banner" role="alert">
                    <IconAlert size={20} />
                    <p>Progres terbaru belum bisa dimuat. Lihat statusnya di dashboard.</p>
                  </div>
                ) : null}

                <ol className="result-list">
                  {progress.map(({ item, progress: state }) => (
                    <ResultItem key={item.position} item={item} state={state} origin={origin} />
                  ))}
                </ol>

                <p className="results-foot">
                  {phase === 'sending' ? 'Mengirim file. Biarkan halaman ini terbuka sampai semua file terkirim. ' : null}
                  <Link href="/">Lihat di dashboard</Link>
                </p>
              </section>
            ) : (
              <form className="card upload-form" onSubmit={(event) => void submit(event)} noValidate>
                <fieldset className="form-section" disabled={locked}>
                  <legend className="form-step">
                    <span className="step-number" aria-hidden="true">
                      1
                    </span>
                    Detail invoice
                  </legend>
                  <div className="form-grid">
                    {/* One field for both shapes, so "+ Klien baru" keeps its place and gets focus back. */}
                    <div className="field">
                      {session.clients.length > 1 ? (
                        <>
                          <label htmlFor="upload-client">Klien</label>
                          <select
                            id="upload-client"
                            value={clientId}
                            onChange={(event) => {
                              setClientId(event.target.value)
                              setClientNote(null)
                              choicesChanged()
                            }}
                          >
                            <option value="" disabled>
                              Pilih klien…
                            </option>
                            {session.clients.map((client) => (
                              <option key={client.id} value={client.id}>
                                {client.name}
                              </option>
                            ))}
                          </select>
                        </>
                      ) : (
                        <>
                          <span className="field-label">Klien</span>
                          <p className="static-value">{session.clients[0].name}</p>
                        </>
                      )}
                      <button
                        type="button"
                        className="link-button field-action"
                        aria-haspopup="dialog"
                        onClick={() => setClientDialog(true)}
                      >
                        + Klien baru
                      </button>
                      {clientNote ? (
                        <p className="field-hint" role="status">
                          {clientNote}
                        </p>
                      ) : null}
                    </div>
                    <div className="field">
                      <label htmlFor="upload-tax">Jenis pajak</label>
                      <select
                        id="upload-tax"
                        value={presetId}
                        required
                        aria-describedby={presetView.kind === 'failed' || preset?.ppn ? 'upload-tax-hint' : undefined}
                        disabled={presetView.kind !== 'ready'}
                        onChange={(event) => {
                          setPresetId(event.target.value)
                          choicesChanged()
                        }}
                      >
                        <option value="">
                          {presetView.kind === 'loading' ? 'Memuat pilihan pajak…' : 'Pilih jenis pajak'}
                        </option>
                        {presets.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                      {presetView.kind === 'failed' ? (
                        <p id="upload-tax-hint" className="field-error">
                          Pilihan pajak belum termuat.{' '}
                          <button type="button" className="link-button" onClick={reload}>
                            Muat ulang
                          </button>
                        </p>
                      ) : preset?.ppn ? (
                        <p id="upload-tax-hint" className="field-hint">
                          Nomor faktur pajak dibaca otomatis dari dokumen.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={hasNpwp}
                      onChange={(event) => {
                        setHasNpwp(event.target.checked)
                        choicesChanged()
                      }}
                    />
                    <span>Penerima punya NPWP/NIK</span>
                  </label>
                </fieldset>

                <fieldset className="form-section" disabled={locked}>
                  <legend className="form-step">
                    <span className="step-number" aria-hidden="true">
                      2
                    </span>
                    File invoice
                  </legend>
                  <label
                    className={dragging ? 'dropzone is-dragging' : 'dropzone'}
                    onDragEnter={onDragOver}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                  >
                    <input
                      className="dropzone-input"
                      type="file"
                      multiple
                      accept={FILE_ACCEPT}
                      onChange={(event) => {
                        addFiles(event.target.files)
                        event.target.value = ''
                      }}
                    />
                    <span className="dropzone-icon" aria-hidden="true">
                      <IconUpload size={26} />
                    </span>
                    <span className="dropzone-title">Tarik invoice ke sini, atau klik untuk memilih.</span>
                    <span className="dropzone-hint">PDF, JPG, atau PNG, maksimal 5 MB per file.</span>
                  </label>

                  {files.length > 0 ? (
                    <>
                      <p className="file-count">
                        {files.length} dari maksimal {MAX_FILES} file
                      </p>
                      <ul className="file-list">
                        {files.map((picked) => (
                          <li key={picked.key} className={picked.problem ? 'file-item has-problem' : 'file-item'}>
                            <span className="file-icon" aria-hidden="true">
                              {picked.kind === 'image' ? <IconImage size={20} /> : <IconFile size={20} />}
                            </span>
                            <span className="file-text">
                              <span className="file-name">{picked.file.name}</span>
                              <span className="file-meta">
                                {formatSize(picked.file.size)}
                                {picked.problem ? (
                                  <span className="file-problem"> · {PROBLEM_NOTES[picked.problem]}</span>
                                ) : null}
                              </span>
                            </span>
                            <button
                              type="button"
                              className="icon-button"
                              onClick={() => removeFile(picked.key)}
                              aria-label={`Hapus ${picked.file.name} dari daftar`}
                            >
                              <IconClose size={18} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  {overLimit ? (
                    <p className="field-error">
                      Maksimal {MAX_FILES} file sekali unggah. Hapus {files.length - MAX_FILES} file dulu.
                    </p>
                  ) : null}
                  {withProblems > 0 && !overLimit ? (
                    <p className="field-hint">
                      File yang bermasalah tetap tercatat lalu ditolak. File lain tetap diproses.
                    </p>
                  ) : null}
                </fieldset>

                {formError ? (
                  <p className="form-error" role="alert">
                    <IconAlert size={18} />
                    <span>{formError}</span>
                  </p>
                ) : null}

                <div className="form-actions">
                  <button type="submit" className="button button-primary button-large" disabled={locked}>
                    {phase === 'preparing' ? (
                      <>
                        <span className="loader loader-small" aria-hidden="true" />
                        Menyiapkan file…
                      </>
                    ) : (
                      <>
                        <IconUpload size={20} />
                        {files.length > 1 ? `Unggah ${files.length} invoice` : 'Unggah invoice'}
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>

          <aside className="card how-card" aria-labelledby="how-title">
            <h2 id="how-title" className="section-title">
              Cara kerjanya
            </h2>
            <ol className="how-steps">
              <li>
                <span className="how-icon how-icon-pink" aria-hidden="true">
                  <IconSparkle size={20} />
                </span>
                <span>
                  <strong>AI membaca invoice Anda.</strong> Vendor, nomor, nominal, dan rekening terisi otomatis.
                </span>
              </li>
              <li>
                <span className="how-icon how-icon-teal" aria-hidden="true">
                  <IconShield size={20} />
                </span>
                <span>
                  <strong>Aturan memeriksa datanya.</strong> Misalnya total, pajak, dan invoice ganda.
                </span>
              </li>
              <li>
                <span className="how-icon how-icon-navy" aria-hidden="true">
                  <IconPerson size={20} />
                </span>
                <span>
                  <strong>Finance yang memutuskan.</strong> Tidak ada yang disetujui otomatis.
                </span>
              </li>
            </ol>
          </aside>
        </div>
      ) : null}

      {clientDialog && session ? (
        <NewClientDialog csrf={session.csrf} onCreated={clientCreated} onClose={() => setClientDialog(false)} />
      ) : null}
    </main>
  )
}

function ResultItem({ item, state, origin }: { item: BatchItem; state: FileProgress; origin: string }) {
  const image = /\.(jpe?g|png)$/i.test(item.filename)
  return (
    <li className={`result-item tone-${state.tone}`}>
      <div className="result-top">
        <span className="file-icon" aria-hidden="true">
          {image ? <IconImage size={20} /> : <IconFile size={20} />}
        </span>
        <span className="file-text">
          <span className="file-name">{item.filename}</span>
          <span className="file-meta">{formatSize(item.byte_size)}</span>
        </span>
        <span className={`badge badge-${state.tone}`}>{state.badge}</span>
      </div>

      <ol className="stepper" aria-label={`Progres ${item.filename}`}>
        {STEP_LABELS.map((label, index) => {
          const step = state.steps[index]
          return (
            <li key={label} className={`step step-${step}`}>
              <span className="step-mark" aria-hidden="true">
                {step === 'done' ? <IconCheck size={14} /> : null}
                {step === 'failed' ? <IconClose size={14} /> : null}
                {step === 'warn' ? '!' : null}
              </span>
              <span className="step-label">
                {label}
                <span className="sr-only">: {STEP_STATE_TEXT[step]}</span>
              </span>
            </li>
          )
        })}
      </ol>

      <div className="result-body">
        <p className="result-title">{state.title}</p>
        {state.detail ? <p className="result-detail">{state.detail}</p> : null}
      </div>

      {state.canOpen && item.request_id ? (
        <a className="button button-secondary button-small result-open" href={reviewUrl(item.request_id, origin)}>
          Buka di layar review
          <IconExternal size={16} />
        </a>
      ) : null}
    </li>
  )
}

/** "+ Klien baru". Mounted only while open, so every opening starts empty; it sits outside the upload form. */
function NewClientDialog({
  csrf,
  onCreated,
  onClose,
}: {
  csrf: string
  onCreated: (created: CreatedClient) => Promise<void>
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const nameInput = useRef<HTMLInputElement>(null)
  const [values, setValues] = useState(EMPTY_CLIENT)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Development runs this twice. No close() in a cleanup: its close event would unmount the dialog.
    if (dialog.current && !dialog.current.open) dialog.current.showModal()
    nameInput.current?.focus()
  }, [])

  const edit = (key: keyof typeof EMPTY_CLIENT, value: string) => setValues((current) => ({ ...current, [key]: value }))
  const close = () => dialog.current?.close()

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (saving) return
    const name = values.name.trim()
    // The server's own wording, so a short name never gets its generic "Data permintaan tidak valid."
    const problem = !name
      ? 'Tulis nama klien dulu.'
      : name.length < 3
        ? 'Tulis nama klien lengkap dengan bentuk usahanya, misalnya CV Sinar Baru Teknik.'
        : null
    if (problem) {
      setError(problem)
      nameInput.current?.focus()
      return
    }
    const optional = (value: string) => value.trim() || null
    const payload = {
      name,
      city: optional(values.city),
      sector: optional(values.sector),
      npwp: optional(values.npwp),
      code: optional(values.code),
    }
    setSaving(true)
    setError(null)
    try {
      // Not aborted on close: a dialog closed mid-save still hands its client to the page.
      const created = await addClient(csrf, payload, new AbortController().signal)
      await onCreated(created)
      // Focus goes back to "+ Klien baru"; the close event then unmounts this dialog.
      close()
    } catch (failure) {
      if (!(failure instanceof ApiError)) console.error(failure)
      setError(asApiError(failure).message)
      setSaving(false)
    }
  }

  return (
    <dialog
      ref={dialog}
      className="card client-dialog"
      aria-labelledby="new-client-title"
      aria-describedby="new-client-lead"
      onCancel={(event) => {
        if (saving) event.preventDefault()
      }}
      onClose={onClose}
    >
      <form onSubmit={(event) => void save(event)} noValidate>
        <div className="dialog-head">
          <div>
            <h2 id="new-client-title">Daftarkan klien baru</h2>
            <p id="new-client-lead" className="dialog-lead">
              Klien langsung terbuka untuk Anda, Finance tim Anda, dan Manajer Keuangan AMIGA.
            </p>
          </div>
          <button type="button" className="icon-button" aria-label="Tutup" disabled={saving} onClick={close}>
            <IconClose size={20} />
          </button>
        </div>

        <div className="field">
          <label htmlFor="new-client-name">Nama klien</label>
          <input
            id="new-client-name"
            ref={nameInput}
            required
            maxLength={120}
            autoComplete="off"
            placeholder="Contoh: CV Sinar Baru Teknik"
            value={values.name}
            onChange={(event) => edit('name', event.target.value)}
          />
        </div>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="new-client-city">Kota</label>
            <input
              id="new-client-city"
              maxLength={60}
              autoComplete="off"
              placeholder="Contoh: Bandung"
              value={values.city}
              onChange={(event) => edit('city', event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-client-sector">Bidang usaha</label>
            <input
              id="new-client-sector"
              maxLength={80}
              autoComplete="off"
              placeholder="Contoh: Servis mesin industri"
              value={values.sector}
              onChange={(event) => edit('sector', event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-client-npwp">NPWP klien (opsional)</label>
            <input
              id="new-client-npwp"
              maxLength={30}
              inputMode="numeric"
              autoComplete="off"
              placeholder="15 atau 16 angka"
              value={values.npwp}
              onChange={(event) => edit('npwp', event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-client-code">Kode voucher (opsional)</label>
            <input
              id="new-client-code"
              maxLength={3}
              autoComplete="off"
              placeholder="Contoh: SBT"
              aria-describedby="new-client-code-hint"
              value={values.code}
              onChange={(event) => edit('code', event.target.value)}
            />
          </div>
        </div>
        <p id="new-client-code-hint" className="field-hint">
          Kode tiga huruf tercetak di depan nomor voucher klien ini. Kosongkan untuk dibuat dari nama klien.
        </p>

        {error ? (
          <p className="form-error" role="alert">
            <IconAlert size={18} />
            <span>{error}</span>
          </p>
        ) : null}

        <div className="dialog-actions">
          <button type="button" className="button button-secondary" disabled={saving} onClick={close}>
            Batal
          </button>
          <button type="submit" className="button button-primary" disabled={saving}>
            {saving ? (
              <>
                <span className="loader loader-small" aria-hidden="true" />
                Menyimpan…
              </>
            ) : (
              'Daftarkan klien'
            )}
          </button>
        </div>
      </form>
    </dialog>
  )
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  const message = error instanceof Error && error.message ? error.message : 'Terjadi kendala tak terduga.'
  return new ApiError('rejected', message)
}

function withoutPosition(states: Record<number, SendState>, position: number): Record<number, SendState> {
  const next = { ...states }
  delete next[position]
  return next
}

/** A file still marked as sending when the run stopped did not get a confirmed answer. */
function markUnconfirmed(states: Record<number, SendState>): Record<number, SendState> {
  const next: Record<number, SendState> = {}
  for (const [key, value] of Object.entries(states)) next[Number(key)] = value === 'sending' ? 'unconfirmed' : value
  return next
}

function keepPositions(states: Record<number, SendState>, positions: Set<number>): Record<number, SendState> {
  const next: Record<number, SendState> = {}
  for (const [key, value] of Object.entries(states)) {
    if (positions.has(Number(key))) next[Number(key)] = value
  }
  return next
}

/** "2 siap direview · 1 ditolak", in the order the badges first appear. */
function summarize(states: FileProgress[]): string {
  const counts = new Map<string, number>()
  for (const state of states) counts.set(state.badge, (counts.get(state.badge) ?? 0) + 1)
  return Array.from(counts, ([badge, count]) => `${count} ${badge.charAt(0).toLowerCase()}${badge.slice(1)}`).join(' · ')
}
