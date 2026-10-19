'use client'

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { IconAlert, IconInbox, IconRefresh, IconSend } from '../../components/icons'
import { useReportAuth } from '../../components/shell'
import { ErrorState, LoadingState, OfflineState, SignedOutState } from '../../components/states'
import {
  addHandoverContact, ApiError, disableHandoverContact, loadHandover, loadSession, sendVoucher,
} from '../../lib/api'
import { formatJakartaDateTime } from '../../lib/format'
import { canUpload } from '../../lib/status'
import type { Handover, HandoverDelivery, HandoverVoucher, Session } from '../../lib/types'

type View =
  | { kind: 'loading' }
  | { kind: 'unauthenticated' }
  | { kind: 'offline' }
  | { kind: 'error'; message: string }
  | { kind: 'not-pic' }
  | { kind: 'ready'; session: Session; data: Handover }

type Outcome = { tone: 'ok' | 'bad'; text: string; proof?: string } | null

const DELIVERY: Record<string, { label: string; tone: string }> = {
  SENDING: { label: 'Sedang dikirim', tone: 'badge' },
  SENT: { label: 'Terkirim', tone: 'badge badge-done' },
  FAILED: { label: 'Gagal terkirim', tone: 'badge badge-rejected' },
  UNCERTAIN: { label: 'Belum pasti', tone: 'badge badge-exception' },
}

function failureOf(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  console.error(error)
  return new ApiError('rejected', 'Terjadi kendala tak terduga.')
}

/** The message n8n sends with the file, as CAPTION_LINES in app/handover_api.py composes it. Keep the two in step. */
function Preview({ voucher, session }: { voucher: HandoverVoucher; session: Session }) {
  return (
    <div className="handover-preview">
      <p>Halo, tim {voucher.client_name}.</p>
      <p>
        Voucher final untuk invoice {voucher.invoice} dari {voucher.vendor} sudah disetujui. File PDF-nya terlampir.
      </p>
      <p><strong>Nomor voucher</strong><br />{voucher.number}</p>
      <p><strong>Nilai bayar</strong><br />{voucher.net_payable_text}</p>
      <p><strong>Disetujui</strong><br />Manajer Keuangan AMIGA, {voucher.approved_at_text}</p>
      <p>Mohon diperiksa, lalu lanjutkan pembayaran ke vendor sesuai proses di tim Anda.</p>
      <p>Salam,<br />{session.name}<br />Admin Intake AMIGA</p>
    </div>
  )
}

function DeliveryBadge({ delivery }: { delivery: HandoverDelivery | null }) {
  if (!delivery) return <span className="badge">Belum dikirim</span>
  const info = DELIVERY[delivery.status] ?? { label: delivery.status, tone: 'badge' }
  return (
    <span className="handover-delivery">
      <span className={info.tone}>{info.label}</span>
      <span className="row-subtitle">
        ke {delivery.contact_name}, {formatJakartaDateTime(delivery.at)}
      </span>
      {delivery.status === 'SENT' && delivery.message_id ? (
        <span className="handover-proof">Bukti Telegram no. {delivery.message_id}</span>
      ) : null}
    </span>
  )
}

export default function HandoverPage() {
  const [view, setView] = useState<View>({ kind: 'loading' })
  const [busy, setBusy] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [contactId, setContactId] = useState('')
  const [checked, setChecked] = useState(false)
  const [sending, setSending] = useState(false)
  const [outcome, setOutcome] = useState<Outcome>(null)
  const [newClient, setNewClient] = useState('')
  const [newName, setNewName] = useState('')
  const [newChat, setNewChat] = useState('')
  const [saving, setSaving] = useState(false)
  const [contactOutcome, setContactOutcome] = useState<Outcome>(null)
  const [confirmDisable, setConfirmDisable] = useState<string | null>(null)
  const inFlight = useRef<AbortController | null>(null)
  const reportAuth = useReportAuth()

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    const controller = new AbortController()
    inFlight.current = controller
    setBusy(true)
    try {
      const session = await loadSession(controller.signal)
      reportAuth({ kind: 'signed-in', name: session.name, role: session.role })
      if (!canUpload(session.role)) {
        setView({ kind: 'not-pic' })
        return
      }
      const data = await loadHandover(controller.signal)
      if (controller.signal.aborted) return
      setView({ kind: 'ready', session, data })
    } catch (error) {
      if (controller.signal.aborted) return
      const failure = failureOf(error)
      if (failure.kind === 'unauthenticated') {
        setView({ kind: 'unauthenticated' })
        reportAuth({ kind: 'signed-out' })
        return
      }
      setView(failure.kind === 'offline' ? { kind: 'offline' } : { kind: 'error', message: failure.message })
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null
        setBusy(false)
      }
    }
  }, [reportAuth])

  useEffect(() => {
    void refresh()
    return () => {
      inFlight.current?.abort()
      inFlight.current = null
    }
  }, [refresh])

  const reload = () => void refresh()
  const ready = view.kind === 'ready' ? view : null
  const opened = ready?.data.vouchers.find((voucher) => voucher.request_id === openId) ?? null
  const recipients = opened && ready ? ready.data.contacts.filter((contact) => contact.client_id === opened.client_id) : []
  const resend = opened?.last_delivery && ['SENT', 'UNCERTAIN'].includes(opened.last_delivery.status)
    ? opened.last_delivery : null

  const open = (voucher: HandoverVoucher) => {
    setOpenId(voucher.request_id)
    const own = ready ? ready.data.contacts.filter((contact) => contact.client_id === voucher.client_id) : []
    setContactId(own.length === 1 ? own[0].id : '')
    setChecked(false)
    setOutcome(null)
  }

  const send = async () => {
    if (!ready || !opened || !contactId || !checked || sending) return
    setSending(true)
    setOutcome(null)
    try {
      const sent = await sendVoucher(ready.session.csrf, opened.request_id, contactId, new AbortController().signal)
      setOutcome({ tone: 'ok', text: `Terkirim ke ${sent.contact_name} lewat Telegram.`,
        proof: `Bukti Telegram no. ${sent.message_id} tercatat di riwayat invoice.` })
      setChecked(false)
    } catch (error) {
      setOutcome({ tone: 'bad', text: failureOf(error).message })
    } finally {
      setSending(false)
      void refresh()
    }
  }

  const addContact = async (event: FormEvent) => {
    event.preventDefault()
    if (!ready || saving) return
    setSaving(true)
    setContactOutcome(null)
    try {
      const contact = await addHandoverContact(ready.session.csrf,
        { client_id: newClient, name: newName, telegram_chat_id: newChat }, new AbortController().signal)
      setContactOutcome({ tone: 'ok', text: `${contact.name} terdaftar sebagai penerima.` })
      setNewName('')
      setNewChat('')
      if (opened && opened.client_id === contact.client_id && !contactId) setContactId(contact.id)
    } catch (error) {
      setContactOutcome({ tone: 'bad', text: failureOf(error).message })
    } finally {
      setSaving(false)
      void refresh()
    }
  }

  const disable = async (id: string) => {
    if (!ready) return
    setConfirmDisable(null)
    try {
      await disableHandoverContact(ready.session.csrf, id, new AbortController().signal)
      if (contactId === id) setContactId('')
    } catch (error) {
      setContactOutcome({ tone: 'bad', text: failureOf(error).message })
    } finally {
      void refresh()
    }
  }

  return (
    <main id="konten" className="page" aria-busy={busy}>
      <div className="page-head">
        <div className="page-heading">
          <h1>Hubungi klien</h1>
          <p className="section-meta">Kirim voucher final yang sudah disetujui ke Telegram klien.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="button button-secondary" onClick={reload}>
            <IconRefresh size={18} className={busy ? 'spin' : undefined} />
            Muat ulang
          </button>
        </div>
      </div>

      {view.kind === 'loading' ? <LoadingState title="Memuat voucher final…" /> : null}
      {view.kind === 'unauthenticated' ? <SignedOutState onRetry={reload} /> : null}
      {view.kind === 'offline' ? <OfflineState onRetry={reload} autoRetry={false} /> : null}
      {view.kind === 'error' ? (
        <ErrorState title="Voucher final belum bisa dimuat." message={view.message} onRetry={reload} />
      ) : null}
      {view.kind === 'not-pic' ? (
        <ErrorState title="Halaman ini untuk PIC."
          message="PIC mengirim voucher final ke klien. Finance dan Manajer Keuangan melihat jejak kirimnya di riwayat invoice." />
      ) : null}

      {ready ? (
        <>
          {ready.data.connected ? null : (
            <div className="banner" role="status">
              <IconAlert size={20} />
              <p>
                <strong>Pengiriman Telegram belum aktif.</strong> Voucher dan penerima tetap bisa disiapkan.
              </p>
            </div>
          )}

          <ol className="handover-steps" aria-label="Cara mengirim voucher">
            {['Pilih voucher', 'Pilih penerima', 'Kirim lewat Telegram'].map((label, index) => {
              const reached = !opened ? 0 : !contactId ? 1 : 2
              const state = index < reached ? 'is-done' : index === reached ? 'is-current' : undefined
              return (
                <li key={label} className={state} aria-current={index === reached ? 'step' : undefined}>
                  <span aria-hidden="true">{index + 1}</span>
                  {label}
                </li>
              )
            })}
          </ol>

          <section className="card queue" aria-labelledby="vouchers-title">
            <div className="queue-head">
              <div>
                <h2 id="vouchers-title" className="section-title">Voucher final siap dikirim</h2>
                <p className="section-meta">Hanya voucher yang sudah disetujui Manajer Keuangan.</p>
              </div>
            </div>
            {ready.data.vouchers.length === 0 ? (
              <div className="state state-inline" role="status">
                <span className="state-icon state-icon-teal">
                  <IconInbox size={24} />
                </span>
                <h2>Belum ada voucher final untuk klien Anda.</h2>
                <p>Voucher muncul di sini begitu Manajer Keuangan menyetujuinya.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="queue-table">
                  <caption className="sr-only">Voucher final per klien</caption>
                  <thead>
                    <tr>
                      <th scope="col">Voucher</th>
                      <th scope="col">Klien</th>
                      <th scope="col">Nilai bayar</th>
                      <th scope="col">Disetujui</th>
                      <th scope="col">Status kirim</th>
                      <th scope="col"><span className="sr-only">Aksi</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {ready.data.vouchers.map((voucher) => (
                      <tr key={voucher.request_id}>
                        <td data-label="Voucher">
                          <span className="row-title">{voucher.number}</span>
                          <span className="row-subtitle">{voucher.invoice} · {voucher.vendor}</span>
                        </td>
                        <td data-label="Klien">{voucher.client_name}</td>
                        <td data-label="Nilai bayar" className="handover-amount">{voucher.net_payable_text}</td>
                        <td data-label="Disetujui">{voucher.approved_at_text}</td>
                        <td data-label="Status kirim"><DeliveryBadge delivery={voucher.last_delivery} /></td>
                        <td data-label="Aksi">
                          <button type="button" className="button button-secondary button-small"
                            aria-expanded={openId === voucher.request_id} onClick={() => open(voucher)}>
                            <IconSend size={16} />
                            Kirim
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {opened ? (
              <section className="handover-panel" aria-labelledby="send-title">
                <h3 id="send-title" className="section-title">Kirim {opened.number} ke Telegram</h3>
                <div className="handover-grid">
                  <div className="field">
                    <label htmlFor="handover-recipient">Penerima</label>
                    <select id="handover-recipient" value={contactId} onChange={(event) => setContactId(event.target.value)}>
                      <option value="">Pilih penerima…</option>
                      {recipients.map((contact) => (
                        <option key={contact.id} value={contact.id}>
                          {contact.name} ({contact.chat_id_masked})
                        </option>
                      ))}
                    </select>
                    {recipients.length === 0 ? (
                      <span className="field-hint">
                        Belum ada penerima untuk {opened.client_name}. Tambahkan di bagian Penerima Telegram di bawah.
                      </span>
                    ) : null}
                  </div>
                  <div className="field">
                    <span className="field-label">Dokumen</span>
                    <span className="static-value">{opened.file_name}</span>
                  </div>
                </div>
                <div className="field">
                  <span className="field-label">Pratinjau pesan Telegram</span>
                  <Preview voucher={opened} session={ready.session} />
                </div>
                {resend ? (
                  <p className="handover-note" role="note">
                    {resend.status === 'SENT'
                      ? `Voucher ini sudah terkirim ke ${resend.contact_name}, ${formatJakartaDateTime(resend.at)}. Kirim lagi hanya kalau memang perlu.`
                      : 'Status kiriman sebelumnya belum pasti. Cek Telegram penerima dulu sebelum mengirim ulang.'}
                  </p>
                ) : null}
                <label className="checkbox">
                  <input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
                  {resend ? 'Saya sudah cek, kirim ulang ke penerima ini.' : 'Penerima dan dokumen sudah saya cek.'}
                </label>
                <div className="handover-actions">
                  <button type="button" className="button button-primary"
                    disabled={!ready.data.connected || !contactId || !checked || sending} onClick={() => void send()}>
                    <IconSend size={18} />
                    {sending ? 'Mengirim…' : 'Kirim ke Telegram'}
                  </button>
                  <button type="button" className="button button-secondary" onClick={() => setOpenId(null)}>
                    Tutup
                  </button>
                </div>
                {outcome ? (
                  <p className={outcome.tone === 'ok' ? 'handover-result is-ok' : 'handover-result is-bad'} role="status">
                    {outcome.text}
                    {outcome.proof ? <span className="handover-proof">{outcome.proof}</span> : null}
                  </p>
                ) : null}
              </section>
            ) : null}
          </section>

          <section className="card queue handover-contacts" aria-labelledby="contacts-title">
            <div className="queue-head">
              <div>
                <h2 id="contacts-title" className="section-title">Penerima Telegram</h2>
                <p className="section-meta">
                  Penerima membuka bot Telegram AMIGA dan menekan Start sekali. Sesudah itu bot boleh mengirim voucher.
                </p>
              </div>
            </div>
            <details className="handover-help">
              <summary>Cara mendapat ID Telegram</summary>
              <ol>
                <li>Minta penerima membuka bot Telegram AMIGA, lalu menekan Start.</li>
                <li>Admin AMIGA melihat ID penerima dari pesan Start yang diterima bot.</li>
                <li>ID akun pribadi berupa angka, misalnya 987654321. ID grup diawali tanda minus, misalnya -1001234567890.</li>
              </ol>
            </details>
            {ready.data.contacts.length ? (
              <div className="table-wrap">
                <table className="queue-table">
                  <caption className="sr-only">Penerima Telegram per klien</caption>
                  <thead>
                    <tr>
                      <th scope="col">Klien</th>
                      <th scope="col">Penerima</th>
                      <th scope="col">ID Telegram</th>
                      <th scope="col"><span className="sr-only">Aksi</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {ready.data.contacts.map((contact) => (
                      <tr key={contact.id}>
                        <td data-label="Klien">
                          {ready.session.clients.find((client) => client.id === contact.client_id)?.name ?? contact.client_id}
                        </td>
                        <td data-label="Penerima">{contact.name}</td>
                        <td data-label="ID Telegram">{contact.chat_id_masked}</td>
                        <td data-label="Aksi">
                          {confirmDisable === contact.id ? (
                            <span className="handover-actions">
                              <button type="button" className="button button-secondary button-small"
                                onClick={() => void disable(contact.id)}>Ya, nonaktifkan</button>
                              <button type="button" className="button button-secondary button-small"
                                onClick={() => setConfirmDisable(null)}>Batal</button>
                            </span>
                          ) : (
                            <button type="button" className="button button-secondary button-small"
                              onClick={() => setConfirmDisable(contact.id)}>Nonaktifkan</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <form className="handover-form" onSubmit={(event) => void addContact(event)}>
              <div className="field">
                <label htmlFor="contact-client">Klien</label>
                <select id="contact-client" value={newClient} required onChange={(event) => setNewClient(event.target.value)}>
                  <option value="">Pilih klien…</option>
                  {ready.session.clients.map((client) => (
                    <option key={client.id} value={client.id}>{client.name}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="contact-name">Nama penerima</label>
                <input id="contact-name" value={newName} required maxLength={80} autoComplete="off"
                  placeholder="Contoh: Bu Rina, Keuangan" onChange={(event) => setNewName(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="contact-chat">ID Telegram</label>
                <input id="contact-chat" value={newChat} required inputMode="numeric" autoComplete="off"
                  placeholder="Contoh: 987654321" onChange={(event) => setNewChat(event.target.value)} />
              </div>
              <div className="handover-actions">
                <button type="submit" className="button button-primary" disabled={saving}>
                  {saving ? 'Menyimpan…' : 'Tambah penerima'}
                </button>
              </div>
              {contactOutcome ? (
                <p className={contactOutcome.tone === 'ok' ? 'handover-result is-ok' : 'handover-result is-bad'}
                  role="status">
                  {contactOutcome.text}
                </p>
              ) : null}
            </form>
          </section>
        </>
      ) : null}
    </main>
  )
}
