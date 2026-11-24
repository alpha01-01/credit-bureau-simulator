import type { Terms } from '../api/game'
import { money, percent } from './format'

/** The deal's terms in a line. */
export function termsLine(t: Terms & { price: string }): string {
  const parts = [`${money(t.price)} a report`, `${t.term_months} months`]
  parts.push(t.service_level === 'PREMIUM' ? 'premium service' : 'standard service')
  if (Number(t.monthly_minimum) > 0) parts.push(`minimum ${money(t.monthly_minimum)} a month`)
  if (Number(t.discount_rate) > 0)
    parts.push(`${percent(Number(t.discount_rate))} off above ${t.discount_threshold} a month`)
  return parts.join(' · ')
}
