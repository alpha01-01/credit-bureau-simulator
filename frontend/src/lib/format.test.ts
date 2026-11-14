import { describe, expect, it } from 'vitest'

import { count, day, formatClock, metricValue, money, percent } from './format'

describe('format', () => {
  it('shows money exactly, in cedis', () => {
    expect(money('1234567.5')).toBe('GHS 1,234,567.50')
    expect(money('-60000')).toBe('-GHS 60,000.00')
    expect(money(null)).toBe('—')
  })

  it('shows counts, shares and dates', () => {
    expect(count(12345)).toBe('12,345')
    expect(percent(0.8512)).toBe('85.1%')
    expect(day('2027-01-04')).toBe('4 Jan 2027')
  })

  it('shows the game clock as a working day and time', () => {
    expect(formatClock({ date: '2027-01-04', time: '08:15' })).toBe('Mon, 4 Jan 2027 · 08:15')
  })

  it('formats metric values by unit', () => {
    expect(metricValue('15000', 'GHS')).toBe('GHS 15,000.00')
    expect(metricValue(0.5, 'share')).toBe('50.0%')
    expect(metricValue(7, 'items')).toBe('7')
  })
})
