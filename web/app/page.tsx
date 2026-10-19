'use client'

import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { IconAlert, IconInbox, IconRefresh, IconSearch } from '../components/icons'
import { useReportAuth } from '../components/shell'
import { ErrorState, LoadingState, OfflineState, SignedOutState } from '../components/states'
import { ApiError, loadDashboard, reviewUrl } from '../lib/api'
import { formatJakartaClock, formatJakartaDateTime, formatRupiah } from '../lib/format'
import { useMainAppOrigin } from '../lib/hooks'
import { approvalStage, canUpload, displayStatus, issueTitle, STATUS_CODES, STATUSES, statusInfo } from '../lib/status'
import type { Dashboard, IssueLabels, QueueRow } from '../lib/types'

const REFRESH_MS = 15_000
const ALL = 'ALL'
const NO_ROWS: QueueRow[] = []

type View =
  | { kind: 'loading' }
  | { kind: 'unauthenticated' }
  | { kind: 'offline' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: Dashboard; problem: string | null }

export default function DashboardPage() {
  // /persetujuan renders this same page, narrowed to the invoices that wait for the viewer's own decision.
  const approvals = usePathname() === '/persetujuan'
  const [view, setView] = useState<View>({ kind: 'loading' })
  const [busy, setBusy] = useState(false)
  const [clientId, setClientId] = useState(ALL)
  const [status, setStatus] = useState(ALL)
  const [search, setSearch] = useState('')
  const inFlight = useRef<AbortController | null>(null)
  const filterOwner = useRef<string | null>(null)
  const reportAuth = useReportAuth()
  const origin = useMainAppOrigin()

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    const controller = new AbortController()
    inFlight.current = controller
    setBusy(true)
    try {
      const data = await loadDashboard(controller.signal)
      if (controller.signal.aborted) return
      const owner = `${data.viewer.role}:${data.viewer.name}`
      if (filterOwner.current !== owner) {
        filterOwner.current = owner
        const params = new URLSearchParams(window.location.search)
        const requested = params.get('status')
        setStatus(requested && STATUS_CODES.includes(requested as typeof STATUS_CODES[number]) ? requested
          : data.viewer.role === 'AMIGA_DIRECTOR' ? 'AMIGA_REVIEWED' : ALL)
        setClientId(params.get('client') || ALL)
      }
      setView({ kind: 'ready', data, problem: null })
      reportAuth({ kind: 'signed-in', name: data.viewer.name, role: data.viewer.role })
    } catch (error) {
      if (controller.signal.aborted) return
      if (!(error instanceof ApiError)) console.error(error)
      const failure =
        error instanceof ApiError ? error : new ApiError('rejected', 'Terjadi kendala tak terduga saat memuat data.')
      if (failure.kind === 'unauthenticated') {
        setView({ kind: 'unauthenticated' })
        reportAuth({ kind: 'signed-out' })
        return
      }
      const fallback: View =
        failure.kind === 'offline' ? { kind: 'offline' } : { kind: 'error', message: failure.message }
      // A failed refresh keeps the last good data on screen and marks it stale.
      setView((previous) => (previous.kind === 'ready' ? { ...previous, problem: failure.message } : fallback))
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null
        setBusy(false)
      }
    }
  }, [reportAuth])

  useEffect(() => {
    void refresh()
    const refreshIfVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    // Coming back after logging in reloads at once: either by switching back to
    // this tab, or by pressing Back when the browser restores the page from cache.
    const refreshIfRestored = (event: PageTransitionEvent) => {
      if (event.persisted) void refresh()
    }
    const timer = window.setInterval(refreshIfVisible, REFRESH_MS)
    document.addEventListener('visibilitychange', refreshIfVisible)
    window.addEventListener('pageshow', refreshIfRestored)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refreshIfVisible)
      window.removeEventListener('pageshow', refreshIfRestored)
      inFlight.current?.abort()
      inFlight.current = null
    }
  }, [refresh])

  const data = view.kind === 'ready' ? view.data : null
  const decides = data ? approvalStage(data.viewer.role) : null
  const rows = useMemo(
    () => (!data ? NO_ROWS : approvals ? data.rows.filter((row) => decides !== null && row.stage === decides) : data.rows),
    [data, approvals, decides],
  )
  const summaryCodes = data?.viewer.role === 'AMIGA_DIRECTOR'
    ? (['AMIGA_REVIEWED', 'AMIGA_APPROVED', 'RETURNED'] as const)
    : data?.viewer.role === 'PIC'
      ? (['INTAKE', 'EXCEPTION', 'READY_FOR_REVIEW'] as const)
      : (['EXCEPTION', 'READY_FOR_REVIEW', 'AMIGA_REVIEWED'] as const)
  const clients = data ? data.viewer.clients : []
  const multiClient = clients.length > 1
  const activeClient = clients.some((client) => client.id === clientId) ? clientId : ALL

  const scoped = useMemo(
    () => (activeClient === ALL ? rows : rows.filter((row) => row.clientId === activeClient)),
    [rows, activeClient],
  )
  const counts = useMemo(() => countByStatus(scoped), [scoped])
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return scoped.filter(
      (row) => (approvals || status === ALL || displayStatus(row) === status) && (needle === '' || searchText(row).includes(needle)),
    )
  }, [scoped, status, search, approvals])

  const reload = () => void refresh()
  const resetFilters = () => {
    setClientId(ALL)
    setStatus(ALL)
    setSearch('')
  }

  return (
    <main id="konten" className="page" aria-busy={busy}>
      <div className="page-head">
        <div className="page-heading">
          <h1>{approvals ? 'Persetujuan' : 'Dashboard antrean'}</h1>
          <ol className="dashboard-flow" aria-label="Alur persetujuan invoice">
            <li>Pengajuan PIC</li>
            <li>Review Finance</li>
            <li>Persetujuan Manajer Keuangan</li>
          </ol>
        </div>
        <div className="page-actions">
          <button type="button" className="button button-secondary" onClick={reload}>
            <IconRefresh size={18} className={busy ? 'spin' : undefined} />
            Muat ulang
          </button>
        </div>
      </div>

      {view.kind === 'loading' ? <LoadingState title="Memuat antrean invoice…" /> : null}
      {view.kind === 'unauthenticated' ? <SignedOutState onRetry={reload} /> : null}
      {view.kind === 'offline' ? <OfflineState onRetry={reload} autoRetry /> : null}
      {view.kind === 'error' ? (
        <ErrorState title="Antrean belum bisa dimuat." message={view.message} onRetry={reload} />
      ) : null}

      {view.kind === 'ready' ? (
        <>
          <p className="refreshed">
            Diperbarui{' '}
            <time dateTime={view.data.refreshedAt.toISOString()}>{formatJakartaClock(view.data.refreshedAt)}</time>
            <button type="button" className="refresh-icon" onClick={reload}
              aria-label="Muat ulang sekarang" title="Muat ulang sekarang">
              <IconRefresh size={16} className={busy ? 'spin' : undefined} />
            </button>
          </p>

          {view.problem ? (
            <div className="banner" role="alert">
              <IconAlert size={20} />
              <p>
                <strong>{view.problem}</strong> Data di bawah dari pemuatan pukul{' '}
                {formatJakartaClock(view.data.refreshedAt)}.
              </p>
              <button type="button" className="button button-secondary button-small" onClick={reload}>
                Coba lagi
              </button>
            </div>
          ) : null}

          {approvals ? null : <section className="summary" aria-labelledby="summary-title">
            <div className="section-head">
              <h2 id="summary-title" className="section-title">
                Ringkasan status
              </h2>
            </div>
            <ul className="tiles">
              <li>
                <button
                  type="button"
                  className="tile tile-total"
                  aria-pressed={status === ALL}
                  onClick={() => setStatus(ALL)}
                >
                  <span className="tile-label">Semua invoice</span>
                  <span className="tile-count">{scoped.length}</span>
                </button>
              </li>
              {summaryCodes.map((code) => (
                <li key={code}>
                  <button
                    type="button"
                    className={`tile tile-${STATUSES[code].tone}`}
                    aria-pressed={status === code}
                    onClick={() => setStatus(status === code ? ALL : code)}
                  >
                    <span className="tile-label">
                      <span className="tile-dot" aria-hidden="true" />
                      {STATUSES[code].label}
                    </span>
                    <span className="tile-count">{counts.get(code) ?? 0}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>}

          <section className="card queue" aria-labelledby="queue-title">
            <div className="queue-head">
              <div>
                <h2 id="queue-title" className="section-title">
                  {approvals ? 'Menunggu keputusan Anda' : 'Daftar invoice'}
                </h2>
              </div>
              <div className="filters" role="group" aria-label="Saring daftar invoice">
                {multiClient ? (
                  <div className="field">
                    <label htmlFor="filter-client">Klien</label>
                    <select
                      id="filter-client"
                      value={activeClient}
                      onChange={(event) => setClientId(event.target.value)}
                    >
                      <option value={ALL}>Semua klien</option>
                      {clients.map((client) => (
                        <option key={client.id} value={client.id}>
                          {client.name}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : null}
                {approvals ? null : <div className="field">
                  <label htmlFor="filter-status">Status</label>
                  <select id="filter-status" value={status} onChange={(event) => setStatus(event.target.value)}>
                    <option value={ALL}>Semua status</option>
                    {STATUS_CODES.map((code) => (
                      <option key={code} value={code}>
                        {STATUSES[code].label}
                      </option>
                    ))}
                  </select>
                </div>}
                <div className="field field-search">
                  <label htmlFor="filter-search">Cari vendor, nomor invoice, atau nama file</label>
                  <div className="input-icon">
                    <IconSearch size={18} />
                    <input
                      id="filter-search"
                      type="search"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Ketik untuk mencari"
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                </div>
              </div>
            </div>

            {visible.length > 0 ? (
              <div className="table-wrap">
                <table className="queue-table">
                  <caption className="sr-only">
                    Invoice, terbaru di atas. Pilih satu baris untuk membukanya di layar review AMIGA.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Invoice</th>
                      {multiClient ? <th scope="col">Klien</th> : null}
                      <th scope="col">Status</th>
                      <th scope="col">Kendala</th>
                      <th scope="col" className="num">
                        Nominal ke vendor
                      </th>
                      <th scope="col">Dibuat (WIB)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((row) => (
                      <QueueRowView
                        key={`${row.clientId}:${row.id}`}
                        row={row}
                        href={reviewUrl(row.id, origin)}
                        labels={view.data.labels}
                        showClient={multiClient}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="state state-inline" role="status">
                <span className="state-icon state-icon-teal">
                  <IconInbox size={24} />
                </span>
                {rows.length === 0 && approvals ? (
                  <>
                    <h2>{decides ? 'Tidak ada invoice yang menunggu keputusan Anda.' : 'Persetujuan untuk Finance dan Manajer Keuangan.'}</h2>
                    <p>{decides === 'FINANCE' ? 'Invoice muncul di sini begitu PIC mengajukannya ke Finance.'
                      : decides === 'DIRECTOR' ? 'Invoice muncul di sini begitu Finance menyetujuinya.'
                      : 'Pantau invoice Anda dari Dashboard.'}</p>
                  </>
                ) : rows.length === 0 ? (
                  <>
                    <h2>Belum ada invoice di antrean.</h2>
                    <p>{data && canUpload(data.viewer.role) ? 'Mulai dari menu Unggah invoice. Hasilnya akan muncul di antrean ini.'
                      : 'Invoice muncul di sini begitu PIC mengunggahnya.'}</p>
                  </>
                ) : (
                  <>
                    <h2>Tidak ada invoice yang cocok.</h2>
                    <p>Coba kata kunci lain, atau longgarkan filter.</p>
                    <div className="state-actions">
                      <button type="button" className="button button-secondary" onClick={resetFilters}>
                        Reset filter
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {view.data.truncated.length > 0 ? (
              <div className="queue-foot">
                <p>
                  AMIGA mengirim maksimal 100 invoice terbaru per klien. Daftar terpotong untuk{' '}
                  {view.data.truncated.join(', ')}.
                </p>
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  )
}

function QueueRowView({
  row,
  href,
  labels,
  showClient,
}: {
  row: QueueRow
  href: string
  labels: IssueLabels
  showClient: boolean
}) {
  const status = statusInfo(displayStatus(row))
  const vendor = row.invoice?.vendor_name?.trim() || null
  const number = row.invoice?.invoice_number?.trim() || null
  const title = vendor ?? row.filename
  const detail = number ? `No. ${number}` : vendor ? row.filename : pendingNote(row.status)
  const subtitle = row.mode === 'REPLAY' ? `${detail} · Contoh` : detail
  const amount = formatRupiah(row.net_payable)

  // The whole row opens the review. The link inside stays the keyboard and
  // screen reader path, and still handles ctrl/middle click for a new tab.
  const openRow = (event: MouseEvent<HTMLTableRowElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if ((event.target as Element).closest('a, button, input, select')) return
    if (window.getSelection()?.toString()) return
    window.location.assign(href)
  }

  return (
    <tr className="queue-row" onClick={openRow}>
      <td className="cell-invoice">
        <a className="row-link" href={href}>
          <span className="row-title">{title}</span>
          <span className="row-subtitle">{subtitle}</span>
        </a>
      </td>
      {showClient ? (
        <td className="cell-client" data-label="Klien">
          {row.clientName}
        </td>
      ) : null}
      <td className="cell-status">
        <span className={`badge badge-${status.tone}`}>{status.label}</span>
      </td>
      <td className="cell-issue" data-label="Kendala">
        <Issue row={row} labels={labels} />
      </td>
      <td className="cell-amount num" data-label="Nominal ke vendor">
        {amount ? <><span>{amount}</span><small className="amount-note">{row.status === 'AMIGA_APPROVED' ? 'Disetujui pada voucher'
          : row.status === 'AMIGA_REVIEWED' ? 'Disetujui Finance · menunggu Manajer Keuangan'
          : row.stage === 'INTAKE' ? 'Masih dalam rencana' : 'Masih dalam pemeriksaan'}</small></> : <span className="amount-pending">Belum ditetapkan</span>}
      </td>
      <td className="cell-created" data-label="Dibuat">
        <time dateTime={row.created_at}>{formatJakartaDateTime(row.created_at)}</time>
      </td>
    </tr>
  )
}

function Issue({ row, labels }: { row: QueueRow; labels: IssueLabels }) {
  if (row.error_code) {
    return (
      <span className="issue">
        <IconAlert size={16} />
        <span>{issueTitle(row.error_code, labels)}</span>
      </span>
    )
  }
  const code = row.issue_codes?.[0]
  const text = row.needs_other_reviewer ? 'Perlu reviewer Finance lain'
    : code ? issueTitle(code, labels)
    : row.source_check_count ? `${row.source_check_count} pemeriksaan sumber oleh Finance`
    : row.status === 'EXCEPTION' ? 'Periksa dokumen dan pilihan pajak'
    : 'Tidak ada kendala otomatis'
  const extra = (row.issue_count || 0) - (code && !row.needs_other_reviewer ? 1 : 0)
  return <span className={code || row.needs_other_reviewer ? 'issue' : 'issue-note'}>
    {code || row.needs_other_reviewer ? <IconAlert size={16} /> : null}
    <span>{text}{extra > 0 ? ` · ${extra} kendala lainnya` : ''}</span>
  </span>
}

function Dash({ label }: { label: string }) {
  return (
    <span className="dash">
      <span className="dash-mark" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  )
}

function pendingNote(status: string): string {
  return status === 'QUEUED' || status === 'PROCESSING' ? 'Menunggu dibaca AI' : 'Data invoice belum terbaca'
}

function searchText(row: QueueRow): string {
  return [row.invoice?.vendor_name, row.invoice?.invoice_number, row.filename].filter(Boolean).join(' ').toLowerCase()
}

function countByStatus(rows: QueueRow[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(displayStatus(row), (counts.get(displayStatus(row)) ?? 0) + 1)
  return counts
}
