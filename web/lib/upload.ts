// Multiple-file intake, ported from app/static/batches.js.
// Flow: manifest first (POST /intake-batches), then one raw POST per pending file,
// then poll the batch while any invoice is still queued or being read.

import { ApiError, apiRequest } from './api'
import { issueTitle, type Tone } from './status'
import type { Batch, BatchItem, IssueLabels, TaxSelection } from './types'

export const MAX_FILES = 5
export const MAX_FILE_BYTES = 5_000_000
export const POLL_MS = 1_500

const TYPES_BY_EXTENSION: ReadonlyMap<string, string> = new Map([
  ['pdf', 'application/pdf'],
  ['jpg', 'image/jpeg'],
  ['jpeg', 'image/jpeg'],
  ['png', 'image/png'],
])
const ACCEPTED_TYPES = new Set(TYPES_BY_EXTENSION.values())

/** Value for the file input's accept attribute. */
export const FILE_ACCEPT = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'

const ZERO_SHA256 = '0'.repeat(64)
const UPLOAD_TIMEOUT_MS = 120_000
const UNREADABLE_BATCH = 'Data unggahan dari AMIGA belum bisa dibaca.'

export type FileProblem = 'unsupported' | 'too-large' | 'empty'

export interface PickedFile {
  /** Stable key for React lists; files may share a name. */
  key: string
  file: File
  kind: 'pdf' | 'image' | 'other'
  problem: FileProblem | null
}

export interface ManifestEntry {
  filename: string
  byte_size: number
  sha256: string
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase()
}

/** Checks the browser can make before anything is sent. The server checks again. */
export function problemOf(file: File): FileProblem | null {
  if (!TYPES_BY_EXTENSION.has(extensionOf(file.name))) return 'unsupported'
  if (file.size > MAX_FILE_BYTES) return 'too-large'
  if (file.size === 0) return 'empty'
  return null
}

export const PROBLEM_NOTES: Record<FileProblem, string> = {
  unsupported: 'Format ini belum didukung. Pakai PDF, JPG, atau PNG.',
  'too-large': 'Lebih dari 5 MB. Perkecil dulu filenya.',
  empty: 'File ini kosong.',
}

let pickCounter = 0

export function pickFile(file: File): PickedFile {
  const extension = extensionOf(file.name)
  pickCounter += 1
  return {
    key: `${pickCounter}-${file.name}-${file.size}-${file.lastModified}`,
    file,
    kind: extension === 'pdf' ? 'pdf' : TYPES_BY_EXTENSION.has(extension) ? 'image' : 'other',
    problem: problemOf(file),
  }
}

/**
 * The file's type as its extension names it. The server rejects a Content-Type that differs
 * from the one the file name implies (app/batches.py, receive), and browsers derive file.type
 * from the extension anyway; file.type is only the fallback for an unlisted extension.
 */
export function contentTypeOf(file: File): string {
  return (
    TYPES_BY_EXTENSION.get(extensionOf(file.name)) ??
    (ACCEPTED_TYPES.has(file.type) ? file.type : 'application/octet-stream')
  )
}

/** "1,2 MB", "840 KB". Decimal units, the same ones as the 5 MB limit. */
export function formatSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1).replace('.', ',')} MB`
  if (bytes >= 1_000) return `${Math.max(1, Math.round(bytes / 1_000))} KB`
  return `${bytes} byte`
}

/**
 * A file that fails the local checks is still listed, so the server records it as rejected.
 * Such files are never read into memory just to hash them (same rule as batches.js).
 */
export async function fileManifest(picked: PickedFile): Promise<ManifestEntry> {
  let sha256 = ZERO_SHA256
  if (!picked.problem) {
    const subtle = globalThis.crypto?.subtle
    if (!subtle) {
      throw new Error('Browser ini belum bisa memeriksa file. Buka halaman ini lewat localhost atau 127.0.0.1.')
    }
    const digest = await subtle.digest('SHA-256', await picked.file.arrayBuffer())
    sha256 = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
  }
  return { filename: picked.file.name, byte_size: picked.file.size, sha256 }
}

/** 8 to 100 characters of [A-Za-z0-9_-], as app/main.py requires. */
export function newIdempotencyKey(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return 'unggah-' + Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function asBatch(body: unknown): Batch {
  if (!isRecord(body) || typeof body.id !== 'string' || !Array.isArray(body.items) || !isRecord(body.counts)) {
    throw new ApiError('rejected', UNREADABLE_BATCH)
  }
  return body as unknown as Batch
}

export async function createBatch(
  csrf: string,
  idempotencyKey: string,
  clientId: string,
  manifests: ManifestEntry[],
  taxSelection: TaxSelection,
  signal: AbortSignal,
): Promise<Batch> {
  const body = await apiRequest('/api/v1/intake-batches', signal, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey, 'x-csrf-token': csrf, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: clientId,
      items: manifests.map((manifest) => ({ ...manifest, tax_selection: taxSelection })),
    }),
  })
  return asBatch(body)
}

export async function uploadBatchItem(
  csrf: string,
  batchId: string,
  position: number,
  file: File,
  signal: AbortSignal,
): Promise<Batch> {
  const body = await apiRequest(`/api/v1/intake-batches/${encodeURIComponent(batchId)}/items/${position}`, signal, {
    method: 'POST',
    headers: { 'Content-Type': contentTypeOf(file), 'x-csrf-token': csrf },
    body: file,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  })
  return asBatch(body)
}

export async function getBatch(batchId: string, signal: AbortSignal): Promise<Batch> {
  return asBatch(await apiRequest(`/api/v1/intake-batches/${encodeURIComponent(batchId)}`, signal))
}

/** Index of the selected file a pending item was created from, or -1. */
export function matchManifest(item: BatchItem, manifests: ManifestEntry[]): number {
  return manifests.findIndex(
    (manifest) =>
      manifest.filename === item.filename && manifest.byte_size === item.byte_size && manifest.sha256 === item.sha256,
  )
}

export function isStillWorking(batch: Batch): boolean {
  return batch.items.some((item) => item.request_status === 'QUEUED' || item.request_status === 'PROCESSING')
}

// Progress per file

export const STEP_LABELS = ['Terkirim', 'Dibaca AI', 'Diperiksa aturan', 'Siap direview'] as const

export type StepState = 'todo' | 'active' | 'done' | 'warn' | 'failed'

/** What the browser knows about sending one file, beyond the server's own record. */
export type SendState = 'sending' | 'unconfirmed'

export interface FileProgress {
  steps: [StepState, StepState, StepState, StepState]
  tone: Tone
  badge: string
  title: string
  detail: string | null
  canOpen: boolean
}

const REUSED_NOTE = 'Invoice yang sama sudah pernah diunggah, jadi kami pakai data yang tersimpan.'

export function progressOf(
  item: BatchItem,
  send: SendState | undefined,
  stillSending: boolean,
  labels: IssueLabels,
): FileProgress {
  if (item.status === 'REJECTED') {
    return {
      steps: ['failed', 'todo', 'todo', 'todo'],
      tone: 'rejected',
      badge: 'Ditolak',
      title: 'File ini tidak bisa kami terima.',
      detail: item.error_message || 'Periksa filenya, lalu unggah lagi.',
      canOpen: false,
    }
  }

  if (item.status !== 'ACCEPTED') {
    if (send === 'sending') {
      return progress(['active', 'todo', 'todo', 'todo'], 'processing', 'Mengirim', 'Sedang mengirim file ini.')
    }
    if (stillSending && send !== 'unconfirmed') {
      return progress(['todo', 'todo', 'todo', 'todo'], 'processing', 'Menunggu', 'Menunggu giliran dikirim.')
    }
    return progress(
      ['warn', 'todo', 'todo', 'todo'],
      'exception',
      'Belum terkirim',
      'File ini belum sampai ke AMIGA.',
      'Coba kirim lagi. File lain tetap aman.',
    )
  }

  const reused = item.request_created === false ? REUSED_NOTE : null
  const canOpen = Boolean(item.request_id)
  const accepted = (
    steps: FileProgress['steps'],
    tone: Tone,
    badge: string,
    title: string,
    detail: string | null = null,
  ): FileProgress => ({ steps, tone, badge, title, detail: detail ?? reused, canOpen })

  switch (item.request_status) {
    case 'QUEUED':
      return accepted(['done', 'active', 'todo', 'todo'], 'processing', 'Dalam antrean', 'Invoice sudah masuk. AI segera membacanya.')
    case 'PROCESSING':
      return accepted(['done', 'active', 'todo', 'todo'], 'processing', 'Dibaca AI', 'AI sedang membaca invoice Anda.')
    case 'READY_FOR_REVIEW':
      return accepted(['done', 'done', 'done', 'done'], 'ready', 'Siap direview', 'Siap direview Finance.')
    case 'AMIGA_REVIEWED':
      return accepted(['done', 'done', 'done', 'done'], 'done', 'Menunggu manajer keuangan', 'Sudah disetujui Finance, menunggu manajer keuangan.')
    case 'AMIGA_APPROVED':
      return accepted(['done', 'done', 'done', 'done'], 'done', 'Disetujui manajer keuangan', 'Voucher invoice ini sudah disetujui manajer keuangan.')
    case 'RETURNED':
      return accepted(['done', 'done', 'warn', 'done'], 'exception', 'Dikembalikan', 'Manajer keuangan mengembalikan invoice ini ke Finance.')
    case 'EXCEPTION':
      if (item.processing_error) {
        return accepted(
          ['done', 'warn', 'todo', 'todo'],
          'exception',
          'Perlu dicek',
          `${issueTitle(item.processing_error, labels)}.`,
          'Finance akan mengeceknya di layar review.',
        )
      }
      return accepted(
        ['done', 'done', 'warn', 'done'],
        'exception',
        'Perlu dicek',
        'Aturan menemukan hal yang perlu dicek.',
        'Invoice tetap masuk ke Finance untuk diperiksa.',
      )
    default:
      return accepted(['done', 'todo', 'todo', 'todo'], 'processing', 'Terkirim', 'Invoice sudah masuk.')
  }
}

function progress(
  steps: FileProgress['steps'],
  tone: Tone,
  badge: string,
  title: string,
  detail: string | null = null,
): FileProgress {
  return { steps, tone, badge, title, detail, canOpen: false }
}
