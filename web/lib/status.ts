import type { IssueLabels } from './types'

export type Tone = 'processing' | 'ready' | 'exception' | 'done' | 'rejected'

/**
 * Backend status codes in pipeline order. Labels match app/static/app.js line 6.
 * INTAKE is a display bucket, not a status: read by AI but not yet submitted by its PIC (see displayStatus).
 */
export const STATUS_CODES = ['QUEUED', 'PROCESSING', 'INTAKE', 'READY_FOR_REVIEW', 'EXCEPTION', 'AMIGA_REVIEWED', 'AMIGA_APPROVED', 'RETURNED'] as const

export type StatusCode = (typeof STATUS_CODES)[number]

export const STATUSES: Record<StatusCode, { label: string; tone: Tone }> = {
  QUEUED: { label: 'Menunggu proses', tone: 'processing' },
  PROCESSING: { label: 'Sedang diproses', tone: 'processing' },
  INTAKE: { label: 'Belum diajukan', tone: 'processing' },
  READY_FOR_REVIEW: { label: 'Siap diperiksa', tone: 'ready' },
  EXCEPTION: { label: 'Perlu perhatian', tone: 'exception' },
  AMIGA_REVIEWED: { label: 'Menunggu manajer keuangan', tone: 'ready' },
  AMIGA_APPROVED: { label: 'Disetujui manajer keuangan', tone: 'done' },
  RETURNED: { label: 'Dikembalikan manajer keuangan', tone: 'rejected' },
}

/**
 * The status a row is shown and filtered by: a read invoice its PIC has not submitted yet counts as INTAKE. A submitted
 * one whose only open items are source checks, which Finance confirms while signing, counts as READY_FOR_REVIEW
 * (app/static/app.js, shownStatus).
 */
export function displayStatus(row: { status: string; stage?: string; current_version: number; issue_count?: number }): string {
  if (row.stage === 'INTAKE' && row.current_version > 0) return 'INTAKE'
  if (row.stage === 'FINANCE' && row.status === 'EXCEPTION' && row.issue_count === 0) return 'READY_FOR_REVIEW'
  return row.status
}

export function statusInfo(code: string): { label: string; tone: Tone } {
  const known = (STATUS_CODES as readonly string[]).includes(code)
  return known ? STATUSES[code as StatusCode] : { label: humanizeCode(code), tone: 'processing' }
}

/**
 * Used only when GET /api/v1/sop/label has no title for a code.
 * Covers the request.error_code values written by app/service.py.
 */
const LOCAL_ISSUE_TITLES = new Map<string, string>([
  ['BUDGET_BLOCKED', 'Batas anggaran AI tercapai'],
  ['EXTRACTION_FAILED', 'AI belum berhasil membaca invoice'],
  ['PROCESS_INTERRUPTED', 'Proses terputus sebelum selesai'],
  ['DOCUMENT_CHANGED', 'Dokumen berubah setelah diunggah'],
  ['TAX_SELECTION_REQUIRED', 'Jenis pajak belum dipilih'],
  ['TAX_NOT_COMPUTED', 'Nominal pajak belum dapat dihitung'],
])

/** "POSSIBLE_DUPLICATE" becomes "Possible duplicate". */
export function humanizeCode(code: string): string {
  const words = code.replace(/[_-]+/g, ' ').trim().toLowerCase()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : code
}

/** Friendly title for an issue code: the server's label first, then local wording, then the code made readable. */
export function issueTitle(code: string, labels: IssueLabels): string {
  const served = Object.prototype.hasOwnProperty.call(labels, code) ? labels[code] : undefined
  return served ?? LOCAL_ISSUE_TITLES.get(code) ?? humanizeCode(code)
}

export function roleLabel(role: string): string {
  if (role === 'PIC') return 'PIC klien'
  if (role === 'FINANCE_REVIEWER') return 'Finance reviewer'
  if (role === 'AMIGA_DIRECTOR') return 'Manajer keuangan'
  return humanizeCode(role)
}

/** Roles that may upload invoices (app/batches.py, BatchService.create). Finance reviews and decides, it does not upload. */
export function canUpload(role: string): boolean {
  return role === 'PIC'
}

/** The queue stage that waits for this role's decision (app/service.py, stage), or null for a role that does not approve. */
export function approvalStage(role: string): 'FINANCE' | 'DIRECTOR' | null {
  if (role === 'FINANCE_REVIEWER') return 'FINANCE'
  if (role === 'AMIGA_DIRECTOR') return 'DIRECTOR'
  return null
}
