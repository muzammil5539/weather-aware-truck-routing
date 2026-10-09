import { describe, expect, it } from 'vitest'
import { formatDuration, formatMiles, formatPounds, nextHour, toLocalInputValue } from './format'

describe('formatDuration', () => {
  it('formats hours and minutes', () => {
    expect(formatDuration(8.5)).toBe('8 hr 30 min')
    expect(formatDuration(2)).toBe('2 hr')
    expect(formatDuration(0.75)).toBe('45 min')
    expect(formatDuration(0)).toBe('0 min')
  })

  it('rounds to the nearest minute', () => {
    expect(formatDuration(1.008)).toBe('1 hr')
  })
})

describe('number formatting', () => {
  it('formats miles and pounds with separators', () => {
    expect(formatMiles(1234.6)).toBe('1,235 mi')
    expect(formatPounds(42000)).toBe('42,000 lb')
  })
})

describe('departure defaults', () => {
  it('rounds up to the next whole hour', () => {
    const result = nextHour(new Date('2026-01-15T12:34:56'))
    expect(result.getHours()).toBe(13)
    expect(result.getMinutes()).toBe(0)
    expect(result.getSeconds()).toBe(0)
  })

  it('produces a datetime-local value in local time', () => {
    const value = toLocalInputValue(new Date(2026, 0, 15, 9, 5))
    expect(value).toBe('2026-01-15T09:05')
  })
})
