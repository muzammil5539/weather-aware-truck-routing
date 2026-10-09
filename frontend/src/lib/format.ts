const TIME = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})
const HOUR = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric' })

export const formatDateTime = (iso: string) => TIME.format(new Date(iso))
export const formatHour = (iso: string) => HOUR.format(new Date(iso))

export function formatDuration(hours: number): string {
  const total = Math.round(hours * 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m} min`
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`
}

export const formatMiles = (miles: number) => `${Math.round(miles).toLocaleString()} mi`

export const formatPounds = (lb: number) => `${Math.round(lb).toLocaleString()} lb`

/** A `datetime-local` input value for the given moment, in the viewer's zone. */
export function toLocalInputValue(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

/** Round up to the next whole hour, the sensible default departure. */
export function nextHour(from: Date = new Date()): Date {
  const next = new Date(from)
  next.setMinutes(0, 0, 0)
  next.setHours(next.getHours() + 1)
  return next
}
