const local = (iso: string) => new Date(`${iso}T00:00:00`)
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function addDays(day: string, n: number): string {
  const d = local(day)
  d.setDate(d.getDate() + n)
  return iso(d)
}

/** "Oct 18 – 24, 2026", or "Sep 27 – Oct 3, 2026" across a month. */
export function weekLabel(start: string, end: string): string {
  const s = local(start), e = local(end)
  const month = (d: Date) => d.toLocaleDateString('en-US', { month: 'short' })
  const tail = s.getMonth() === e.getMonth() ? `${e.getDate()}` : `${month(e)} ${e.getDate()}`
  return `${month(s)} ${s.getDate()} – ${tail}, ${e.getFullYear()}`
}
