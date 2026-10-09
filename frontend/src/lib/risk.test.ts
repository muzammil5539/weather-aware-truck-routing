import { describe, expect, it } from 'vitest'
import {
  RISK_COLOR,
  RISK_LABEL,
  RISK_ORDER,
  colorFromScore,
  isBlocked,
  levelFromScore,
  riskSummary,
} from './risk'

describe('risk levels', () => {
  it('orders levels from least to most dangerous', () => {
    expect(RISK_ORDER).toEqual(['low', 'moderate', 'high', 'severe', 'no_travel'])
  })

  it('maps each backend score to its level', () => {
    expect([0, 1, 2, 3, 4].map(levelFromScore)).toEqual(RISK_ORDER)
  })

  it('clamps scores outside the scale', () => {
    expect(levelFromScore(-5)).toBe('low')
    expect(levelFromScore(99)).toBe('no_travel')
  })

  it('gives every level a label and a distinct colour', () => {
    const colors = RISK_ORDER.map((level) => RISK_COLOR[level])
    expect(new Set(colors).size).toBe(RISK_ORDER.length)
    for (const level of RISK_ORDER) expect(RISK_LABEL[level]).toBeTruthy()
  })

  it('darkens steadily as risk rises, so the ramp survives colour blindness', () => {
    const luminance = (hex: string) => {
      const n = parseInt(hex.slice(1), 16)
      return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)
    }
    const severe = luminance(RISK_COLOR.severe)
    expect(luminance(RISK_COLOR.no_travel)).toBeLessThan(severe)
    expect(severe).toBeLessThan(luminance(RISK_COLOR.moderate))
  })

  it('colours by rounded score', () => {
    expect(colorFromScore(3.4)).toBe(RISK_COLOR.severe)
  })
})

describe('riskSummary', () => {
  it('lists the worst conditions first', () => {
    const summary = riskSummary({ no_travel: 10, severe: 20, high: 0, moderate: 5, low: 100 })
    expect(summary).toBe('10 miles No Travel, 20 miles Severe, 5 miles Moderate, 100 miles Low')
  })

  it('handles a route with no mileage', () => {
    expect(riskSummary({ no_travel: 0, severe: 0, high: 0, moderate: 0, low: 0 })).toBe(
      'No risk data',
    )
  })
})

describe('isBlocked', () => {
  it('is true only when some miles are No Travel', () => {
    expect(isBlocked({ no_travel: 0.0 })).toBe(false)
    expect(isBlocked({ no_travel: 12 })).toBe(true)
  })
})
