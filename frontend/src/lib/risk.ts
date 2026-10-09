import type { RiskLevel, RiskMiles } from '../api/types'

export const RISK_ORDER: RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
}

/**
 * The risk ramp. Hue alone does not separate these for a colour-blind driver,
 * so lightness drops steadily from Low to No Travel as well.
 */
export const RISK_COLOR: Record<RiskLevel, string> = {
  low: '#1a7f5a',
  moderate: '#8a6508',
  high: '#a04e12',
  severe: '#b3261e',
  no_travel: '#5b0f0a',
}

/** Text colour that keeps 4.5:1 against the matching RISK_COLOR fill. */
export const RISK_TEXT: Record<RiskLevel, string> = {
  low: '#ffffff',
  moderate: '#ffffff',
  high: '#ffffff',
  severe: '#ffffff',
  no_travel: '#ffffff',
}

export function levelFromScore(score: number): RiskLevel {
  return RISK_ORDER[Math.max(0, Math.min(RISK_ORDER.length - 1, Math.round(score)))]
}

export function colorFromScore(score: number): string {
  return RISK_COLOR[levelFromScore(score)]
}

export const RISK_THRESHOLDS = {
  wind_mph: [25, 35, 45, 55],
  rain_in_hr: [0.1, 0.25, 0.5, 1.0],
  snow_in_hr: [0.5, 1.0, 2.0, 3.0],
} as const

export const DRIVER_LABEL: Record<string, string> = {
  wind: 'Wind',
  rain: 'Rain',
  snow: 'Snow',
  load: 'Load rule',
}

/** Is this route safe to dispatch at all? */
export function isBlocked(riskMiles: { no_travel: number }): boolean {
  return riskMiles.no_travel > 0
}

/** Spoken-word description of a route's risk mix, for screen readers. */
export function riskSummary(riskMiles: RiskMiles): string {
  const parts = (['no_travel', 'severe', 'high', 'moderate', 'low'] as RiskLevel[])
    .filter((level) => (riskMiles[level] ?? 0) > 0)
    .map((level) => `${Math.round(riskMiles[level])} miles ${RISK_LABEL[level]}`)
  return parts.length ? parts.join(', ') : 'No risk data'
}
