import type { Route, Trip } from '../api/types'
import { formatDateTime, formatDuration, formatMiles, formatPounds } from '../lib/format'
import { RISK_LABEL } from '../lib/risk'

export function TripSummary({ trip, route }: { trip: Trip; route: Route }) {
  return (
    <div className="summarygrid">
      <div>
        <b>Load</b>
        <span>{formatPounds(trip.load_lb)}</span>
      </div>
      <div>
        <b>Departs</b>
        <span>{formatDateTime(trip.departure_at)}</span>
      </div>
      <div>
        <b>Distance</b>
        <span>{formatMiles(route.distance_miles)}</span>
      </div>
      <div>
        <b>Drive time</b>
        <span>{formatDuration(route.duration_hours)}</span>
      </div>
      <div>
        <b>Arrives</b>
        <span>{formatDateTime(route.arrival_at)}</span>
      </div>
      <div>
        <b>Checkpoints</b>
        <span>
          {route.checkpoints.length} · every {trip.checkpoint_interval_miles} mi
        </span>
      </div>
      <div>
        <b>Worst conditions</b>
        <span>{RISK_LABEL[route.worst_level]}</span>
      </div>
      <div>
        <b>Avg risk</b>
        <span>{route.average_risk.toFixed(2)} / 4</span>
      </div>
    </div>
  )
}
