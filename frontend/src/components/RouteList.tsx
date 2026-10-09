import type { Route } from '../api/types'
import { formatDateTime, formatDuration, formatMiles } from '../lib/format'
import { RiskBar, RiskPill } from './RiskPill'

interface Props {
  routes: Route[]
  selectedRouteName: string
  onSelect: (name: string) => void
}

export function RouteList({ routes, selectedRouteName, onSelect }: Props) {
  return (
    <ul className="routes">
      {routes.map((route) => (
        <li key={route.name}>
          <button
            type="button"
            className="route"
            aria-pressed={route.name === selectedRouteName}
            onClick={() => onSelect(route.name)}
          >
            <span className="route__top">
              <span className="route__name">{route.name}</span>
              {route.is_recommended && <span className="route__badge">Recommended</span>}
              <span style={{ marginLeft: 'auto' }}>
                <RiskPill level={route.worst_level} title="Worst conditions on this route" />
              </span>
            </span>

            <span className="route__summary" title={route.summary}>
              {route.summary}
              {route.source === 'detour' && ' · alternate corridor'}
            </span>

            <RiskBar riskMiles={route.risk_miles} total={route.distance_miles} />

            <span className="route__stats">
              <span className="num">
                <b>Distance</b>
                {formatMiles(route.distance_miles)}
              </span>
              <span className="num">
                <b>Drive time</b>
                {formatDuration(route.duration_hours)}
              </span>
              <span className="num">
                <b>Arrives</b>
                {formatDateTime(route.arrival_at)}
              </span>
              <span className="num">
                <b>Avg risk</b>
                {route.average_risk.toFixed(2)}
              </span>
            </span>

            {route.warnings.map((warning) => (
              <span className="route__warning" key={warning}>
                {warning}
              </span>
            ))}
          </button>
        </li>
      ))}
    </ul>
  )
}
