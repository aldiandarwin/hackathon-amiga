// Display formatters. Every time on this screen is shown in Asia/Jakarta (WIB),
// whatever the viewer's own time zone is.

const MONTHS_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

// en-GB only supplies numeric parts. Month names come from MONTHS_ID, so the
// output does not depend on the browser's Indonesian locale data.
const jakarta = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Jakarta',
  year: 'numeric',
  month: 'numeric',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

function jakartaParts(date: Date): Record<string, string> {
  const parts: Record<string, string> = {}
  for (const part of jakarta.formatToParts(date)) parts[part.type] = part.value
  return parts
}

/** "2026-10-14T02:12:00+00:00" becomes "14 Okt 2026 09:12". */
export function formatJakartaDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const p = jakartaParts(date)
  return `${p.day} ${MONTHS_ID[Number(p.month) - 1]} ${p.year} ${p.hour}:${p.minute}`
}

/** "09:12:05 WIB" */
export function formatJakartaClock(date: Date): string {
  const p = jakartaParts(date)
  return `${p.hour}:${p.minute}:${p.second} WIB`
}

/**
 * "6156000.00" becomes "Rp 6.156.000". A non-zero fraction is kept ("Rp 1.500,50").
 * Works on the decimal string itself, so large amounts never lose precision.
 * Returns null for null input. An unexpected format is returned unchanged.
 */
export function formatRupiah(value: string | null | undefined): string | null {
  if (value == null) return null
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!match) return value
  const [, sign, whole, fraction = ''] = match
  const grouped = whole.replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  const cents = /[1-9]/.test(fraction) ? `,${fraction.padEnd(2, '0')}` : ''
  return `${sign}Rp ${grouped}${cents}`
}
