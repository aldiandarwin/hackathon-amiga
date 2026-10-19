import type {
  ClientRef, CreatedClient, Dashboard, Handover, HandoverContact, HandoverSent, IssueLabels, QueueRow, RequestItem, Session,
  TaxPreset, Viewer,
} from './types'

/** Public browser entry point; Next.js proxies the FastAPI workspace and API. */
export const MAIN_APP_PORT = '3000'

/** Used only while rendering on the server, before the browser's own host is known. */
export const FALLBACK_MAIN_APP_ORIGIN = `http://127.0.0.1:${MAIN_APP_PORT}`

export const OFFLINE_MESSAGE = 'Layanan AMIGA belum bisa dihubungi.'

export const SESSION_CHANGED_MESSAGE = 'Sesi berubah. Muat ulang halaman.'

const UNREADABLE_MESSAGE = 'Data dari AMIGA belum bisa dibaca.'
const TIMEOUT_MS = 12_000

/**
 * The main app on the same host as this page, so localhost stays localhost.
 * The session cookie is scoped to the host name, so switching hosts would log the user out.
 */
export function mainAppOrigin(): string {
  if (typeof window === 'undefined') return FALLBACK_MAIN_APP_ORIGIN
  return window.location.origin
}

/** Deep link the main app opens on load. */
export function reviewUrl(requestId: string, origin: string = mainAppOrigin()): string {
  return `${origin}/review#request=${encodeURIComponent(requestId)}`
}

export type FailureKind = 'unauthenticated' | 'offline' | 'rejected'

export class ApiError extends Error {
  readonly kind: FailureKind
  /** HTTP status, or null when no response arrived. */
  readonly status: number | null
  /** The backend's error code, such as CSRF_REJECTED. */
  readonly code: string | null

  constructor(kind: FailureKind, message: string, status: number | null = null, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isClient(value: unknown): value is ClientRef {
  return isRecord(value) && typeof value.id === 'string' && typeof value.name === 'string'
}

export interface RequestOptions {
  method?: 'GET' | 'POST'
  headers?: Record<string, string>
  body?: BodyInit
  timeoutMs?: number
}

/**
 * Same-origin call to the backend; next.config.ts proxies /api/v1 to FastAPI.
 * Every POST needs the session's CSRF token in x-csrf-token, which the caller adds.
 */
export async function apiRequest(path: string, signal: AbortSignal, options: RequestOptions = {}): Promise<unknown> {
  const local = new AbortController()
  const timer = setTimeout(() => local.abort(), options.timeoutMs ?? TIMEOUT_MS)
  const forwardAbort = () => local.abort()
  signal.addEventListener('abort', forwardAbort)
  try {
    let response: Response
    try {
      response = await fetch(path, {
        method: options.method ?? 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json', ...options.headers },
        body: options.body,
        signal: local.signal,
      })
    } catch (error) {
      if (signal.aborted) throw error
      // Network failure or timeout: the proxy or FastAPI is not answering.
      throw new ApiError('offline', OFFLINE_MESSAGE)
    }
    const body: unknown = await response.json().catch(() => null)
    const code = isRecord(body) && typeof body.code === 'string' ? body.code : null
    if (response.status === 401) throw new ApiError('unauthenticated', 'Sesi belum aktif.', 401, code)
    if (response.status === 403 && (code === 'CSRF_REJECTED' || code === 'ORIGIN_REJECTED')) {
      throw new ApiError('rejected', SESSION_CHANGED_MESSAGE, 403, code)
    }
    // The Next proxy answers 500 when FastAPI is down, so 5xx means "not up".
    if (response.status >= 500) throw new ApiError('offline', OFFLINE_MESSAGE, response.status, code)
    if (!response.ok) {
      const message = isRecord(body) && typeof body.message === 'string' ? body.message : null
      throw new ApiError(
        'rejected',
        message ?? `AMIGA belum bisa memproses ini (kode ${response.status}).`,
        response.status,
        code,
      )
    }
    return body
  } finally {
    clearTimeout(timer)
    signal.removeEventListener('abort', forwardAbort)
  }
}

function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  return apiRequest(path, signal)
}

/** The full session, CSRF token included. Only the upload page needs the token. */
export async function loadSession(signal: AbortSignal): Promise<Session> {
  const body = await getJson('/api/v1/session', signal)
  if (!isRecord(body) || typeof body.name !== 'string' || !Array.isArray(body.clients)) {
    throw new ApiError('rejected', UNREADABLE_MESSAGE)
  }
  return {
    id: typeof body.id === 'string' ? body.id : '',
    name: body.name,
    role: typeof body.role === 'string' ? body.role : '',
    csrf: typeof body.csrf === 'string' ? body.csrf : '',
    clients: body.clients.filter(isClient),
  }
}

async function getViewer(signal: AbortSignal): Promise<Viewer> {
  const { name, role, clients } = await loadSession(signal)
  return { name, role, clients }
}

async function getRequests(client: ClientRef, signal: AbortSignal) {
  const body = await getJson(`/api/v1/requests?client_id=${encodeURIComponent(client.id)}`, signal)
  if (!isRecord(body) || !Array.isArray(body.items)) throw new ApiError('rejected', UNREADABLE_MESSAGE)
  const items = body.items as RequestItem[]
  const limit = typeof body.limit === 'number' ? body.limit : Number.POSITIVE_INFINITY
  return { client, items, truncated: items.length >= limit }
}

const NO_LABELS: IssueLabels = Object.freeze({})
let labelCache: Promise<IssueLabels> | null = null

/**
 * Friendly titles per issue code, fetched once per page load and shared by every screen.
 * Never throws: on failure the caller falls back to its own wording, and the next
 * call tries again. Only a successful answer is kept.
 */
export function loadIssueLabels(): Promise<IssueLabels> {
  if (!labelCache) {
    // Its own signal: a dashboard refresh that is cancelled must not cancel the shared fetch.
    const attempt = getJson('/api/v1/sop/label', new AbortController().signal).then((body) => {
      const labels = isRecord(body) && isRecord(body.labels) ? body.labels : {}
      const clean: Record<string, string> = {}
      for (const [code, title] of Object.entries(labels)) {
        if (typeof title === 'string' && title.trim() !== '') clean[code] = title.trim()
      }
      return Object.freeze(clean) as IssueLabels
    })
    labelCache = attempt.catch(() => {
      labelCache = null
      return NO_LABELS
    })
  }
  return labelCache
}

/** Tax presets of GET /api/v1/tax/rules, in server order. */
export async function loadTaxPresets(signal: AbortSignal): Promise<TaxPreset[]> {
  const body = await getJson('/api/v1/tax/rules', signal)
  if (!isRecord(body) || !Array.isArray(body.presets)) throw new ApiError('rejected', UNREADABLE_MESSAGE)
  return body.presets.filter(
    (preset): preset is TaxPreset =>
      isRecord(preset) &&
      typeof preset.id === 'string' &&
      typeof preset.label === 'string' &&
      typeof preset.pph === 'string' &&
      typeof preset.ppn === 'boolean',
  )
}

function timeOf(iso: string): number {
  const time = Date.parse(iso)
  return Number.isNaN(time) ? 0 : time
}

const LABEL_WAIT_MS = 2_500

/** Labels never hold the queue back: a slow answer is used from the next refresh on. */
function issueLabelsSoon(): Promise<IssueLabels> {
  return Promise.race([
    loadIssueLabels(),
    new Promise<IssueLabels>((resolve) => setTimeout(() => resolve(NO_LABELS), LABEL_WAIT_MS)),
  ])
}

/** Session first, then every assigned client's queue in parallel, merged newest first. */
export async function loadDashboard(signal: AbortSignal): Promise<Dashboard> {
  const viewer = await getViewer(signal)
  const [lists, labels] = await Promise.all([
    Promise.all(viewer.clients.map((client) => getRequests(client, signal))),
    issueLabelsSoon(),
  ])
  const rows: QueueRow[] = lists.flatMap(({ client, items }) =>
    items.map((item) => ({ ...item, clientId: client.id, clientName: client.name })),
  )
  rows.sort((a, b) => timeOf(b.created_at) - timeOf(a.created_at))
  return {
    viewer,
    rows,
    truncated: lists.filter((list) => list.truncated).map((list) => list.client.name),
    labels,
    refreshedAt: new Date(),
  }
}

// Hubungi klien (app/handover_api.py): the PIC sends a final voucher to the client's Telegram through n8n.

/** n8n answers once Telegram holds the file; the backend cuts a hung call at 25 s, so this waits a little longer. */
const SEND_TIMEOUT_MS = 40_000

function postJson(path: string, csrf: string, payload: unknown, signal: AbortSignal, timeoutMs?: number) {
  return apiRequest(path, signal, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-csrf-token': csrf },
    body: JSON.stringify(payload),
    timeoutMs,
  })
}

export async function loadHandover(signal: AbortSignal): Promise<Handover> {
  const body = await getJson('/api/v1/handover', signal)
  if (!isRecord(body) || !Array.isArray(body.vouchers) || !Array.isArray(body.contacts)) {
    throw new ApiError('rejected', UNREADABLE_MESSAGE)
  }
  return {
    connected: body.connected === true,
    vouchers: body.vouchers as Handover['vouchers'],
    contacts: body.contacts as HandoverContact[],
  }
}

export async function addHandoverContact(
  csrf: string,
  contact: { client_id: string; name: string; telegram_chat_id: string },
  signal: AbortSignal,
): Promise<HandoverContact> {
  const body = await postJson('/api/v1/handover/contacts', csrf, contact, signal)
  if (!isRecord(body) || !isRecord(body.contact)) throw new ApiError('rejected', UNREADABLE_MESSAGE)
  return body.contact as unknown as HandoverContact
}

export async function disableHandoverContact(csrf: string, contactId: string, signal: AbortSignal): Promise<void> {
  await postJson(`/api/v1/handover/contacts/${encodeURIComponent(contactId)}/disable`, csrf, {}, signal)
}

export async function sendVoucher(
  csrf: string,
  requestId: string,
  contactId: string,
  signal: AbortSignal,
): Promise<HandoverSent> {
  const body = await postJson('/api/v1/handover/send', csrf, { request_id: requestId, contact_id: contactId }, signal,
    SEND_TIMEOUT_MS)
  if (!isRecord(body) || typeof body.message_id !== 'string') throw new ApiError('rejected', UNREADABLE_MESSAGE)
  return body as unknown as HandoverSent
}

// Klien baru (app/clients.py): a PIC opens a client for the team; the server checks name, NPWP and code again.

export async function addClient(
  csrf: string,
  client: { name: string; city: string | null; sector: string | null; npwp: string | null; code: string | null },
  signal: AbortSignal,
): Promise<CreatedClient> {
  const body = await postJson('/api/v1/clients', csrf, client, signal)
  const created = isRecord(body) ? body.client : null
  if (!isRecord(body) || !isRecord(created) || !isClient(created) || typeof created.code !== 'string') {
    throw new ApiError('rejected', UNREADABLE_MESSAGE)
  }
  const members = Array.isArray(body.members) ? body.members.filter((name): name is string => typeof name === 'string') : []
  return { client: { id: created.id, name: created.name, code: created.code }, members }
}
