import type { RiskLevel, RiskMiles } from '../api/types'
import { RISK_COLOR, RISK_LABEL, riskSummary } from '../lib/risk'

export function RiskPill({ level, title }: { level: RiskLevel; title?: string }) {
  return (
    <span className="pill" style={{ background: RISK_COLOR[level] }} title={title}>
      {RISK_LABEL[level]}
    </span>
  )
}

/** Proportional bar of a route's miles by risk level. */
export function RiskBar({ riskMiles, total }: { riskMiles: RiskMiles; total: number }) {
  const order: RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel']
  const sum = total || order.reduce((acc, level) => acc + (riskMiles[level] ?? 0), 0) || 1
  return (
    <div className="riskbar" role="img" aria-label={riskSummary(riskMiles)}>
      {order.map((level) => {
        const miles = riskMiles[level] ?? 0
        if (miles <= 0) return null
        return (
          <span
            key={level}
            style={{ flex: miles / sum, background: RISK_COLOR[level] }}
            title={`${RISK_LABEL[level]}: ${Math.round(miles)} mi`}
          />
        )
      })}
    </div>
  )
}
