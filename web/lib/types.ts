// Shapes returned by the FastAPI backend (app/main.py).

export interface ClientRef {
  id: string
  name: string
}

/** POST /api/v1/clients (app/clients.py, ClientService.create): the new client and everyone who now holds it. */
export interface CreatedClient {
  client: ClientRef & { code: string }
  members: string[]
}

/**
 * GET /api/v1/session, as the upload page needs it.
 * The CSRF token must accompany every POST, so only the upload page keeps it.
 */
export interface Session {
  id: string
  name: string
  role: string
  csrf: string
  clients: ClientRef[]
}

/** GET /api/v1/session, reduced to what the dashboard shows. */
export interface Viewer {
  name: string
  role: string
  clients: ClientRef[]
}

/** Invoice snapshot fields this screen reads (see prototype/amiga_ocr/contracts.py). */
export interface InvoiceSnapshot {
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  currency: string | null
  stated_total: string | null
}

/** One item of GET /api/v1/requests?client_id=... */
export interface RequestItem {
  id: string
  filename: string
  status: string
  current_version: number
  created_at: string
  mode: string
  error_code: string | null
  invoice: InvoiceSnapshot | null
  /** Decimal string such as "6156000.00", or null before tax is computed. */
  net_payable: string | null
  issue_codes?: string[]
  issue_count?: number
  source_check_count?: number
  needs_other_reviewer?: boolean
  /** INTAKE until the PIC submits, then FINANCE, DIRECTOR, FINAL (app/service.py, stage). */
  stage?: string
  submitted_at?: string | null
}

export interface QueueRow extends RequestItem {
  clientId: string
  clientName: string
}

/** Friendly titles per check or error code, from GET /api/v1/sop/label. */
export type IssueLabels = Readonly<Record<string, string>>

export interface Dashboard {
  viewer: Viewer
  /** Every client's requests merged, newest first. */
  rows: QueueRow[]
  /** Names of clients whose list hit the backend limit (100 newest). */
  truncated: string[]
  labels: IssueLabels
  refreshedAt: Date
}

/** One preset of GET /api/v1/tax/rules (app/tax_api.py, TaxPreset). */
export interface TaxPreset {
  id: string
  label: string
  pph: string
  ppn: boolean
}

/** Body of tax_selection in a batch manifest (app/tax_api.py, TaxSelection). */
export interface TaxSelection {
  pph: string
  ppn: boolean
  recipient_has_npwp: boolean
  faktur_number: null
}

export type BatchItemStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED'

/** One file of a batch (app/batches.py, BatchService.detail). */
export interface BatchItem {
  position: number
  filename: string
  byte_size: number
  sha256: string
  status: BatchItemStatus | string
  request_id: string | null
  request_created: boolean | null
  error_code: string | null
  error_message: string | null
  /** Status of the invoice the file became, once accepted. */
  request_status: string | null
  /** Error code of that invoice, for example when AI could not read it. */
  processing_error: string | null
}

/** The last send of a final voucher (app/handover_api.py). SENT only with Telegram's message id as proof. */
export interface HandoverDelivery {
  status: 'SENDING' | 'SENT' | 'FAILED' | 'UNCERTAIN' | string
  contact_name: string
  at: string
  message_id: string | null
}

/** One final voucher of GET /api/v1/handover. */
export interface HandoverVoucher {
  request_id: string
  client_id: string
  client_name: string
  number: string
  invoice: string
  vendor: string
  net_payable_text: string
  approved_at: string
  approved_at_text: string
  file_name: string
  last_delivery: HandoverDelivery | null
}

/** A client's Telegram recipient; the chat id stays masked on screen. */
export interface HandoverContact {
  id: string
  client_id: string
  name: string
  chat_id_masked: string
}

/** GET /api/v1/handover, for the PIC's Hubungi klien page. */
export interface Handover {
  connected: boolean
  vouchers: HandoverVoucher[]
  contacts: HandoverContact[]
}

/** POST /api/v1/handover/send once Telegram confirmed the file. */
export interface HandoverSent {
  status: string
  message_id: string
  contact_name: string
}

/** GET /api/v1/intake-batches/{id}, also returned by every batch POST. */
export interface Batch {
  id: string
  client_id: string
  items: BatchItem[]
  counts: { pending: number; accepted: number; rejected: number }
  upload_complete: boolean
  can_upload: boolean
}
