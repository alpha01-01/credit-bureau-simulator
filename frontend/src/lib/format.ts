/** Display helpers. Amounts arrive from the API as decimal strings (exact money). */

const ghs = new Intl.NumberFormat('en-GH', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const whole = new Intl.NumberFormat('en-GH')

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const amount = Number(value)
  return `${amount < 0 ? '-' : ''}GHS ${ghs.format(Math.abs(amount))}`
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : whole.format(value)
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

export function day(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value.length === 10 ? `${value}T00:00:00Z` : value)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  })
}

export function metricValue(value: unknown, unit: string): string {
  if (unit === 'GHS') return money(value as string)
  if (unit === 'share') return percent(value as number | null)
  return count(value as number | null)
}

export function formatClock(clock: { date: string; time: string }): string {
  const date = new Date(`${clock.date}T00:00:00Z`).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
  return `${date} · ${clock.time}`
}
