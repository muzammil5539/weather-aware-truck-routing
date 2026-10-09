import type { Route, Trip } from '../api/types'
import { CheckpointTable } from '../components/CheckpointTable'
import { HourSlider } from '../components/HourSlider'
import { RiskLegend, RiskReference } from '../components/RiskLegend'
import { TripMap } from '../components/TripMap'
import { TripSummary } from '../components/TripSummary'

interface Props {
  trip: Trip
  route: Route
  onSelectRoute: (name: string) => void
  heatHour: number
  onHeatHourChange: (hour: number) => void
  showHeatmap: boolean
  onShowHeatmapChange: (show: boolean) => void
}

/** The map, corridor heatmap and checkpoint table for the selected route. */
export function TripView({
  trip,
  route,
  onSelectRoute,
  heatHour,
  onHeatHourChange,
  showHeatmap,
  onShowHeatmapChange,
}: Props) {
  const hours = trip.heatmap?.hours ?? []

  return (
    <>
      <section className="panel" aria-labelledby="map-heading">
        <div className="panel__head">
          <h2 id="map-heading">
            {trip.origin.label.split(',')[0]} → {trip.destination.label.split(',')[0]}
          </h2>
          <RiskLegend />
        </div>
        <div className="panel__body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <TripSummary trip={trip} route={route} />
          <TripMap
            trip={trip}
            selectedRouteName={route.name}
            onSelectRoute={onSelectRoute}
            heatHour={heatHour}
            showHeatmap={showHeatmap}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0 }}>Weather along the corridor</h3>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.84rem' }}>
                <input
                  type="checkbox"
                  checked={showHeatmap}
                  onChange={(e) => onShowHeatmapChange(e.target.checked)}
                />
                Show heatmap
              </label>
              <span className="panel__hint" style={{ marginLeft: 'auto' }}>
                Forecast risk across the whole corridor, 0–{hours.length - 1} h from departure.
              </span>
            </div>
            <HourSlider hours={hours} value={heatHour} onChange={onHeatHourChange} />
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="checkpoints-heading">
        <div className="panel__head">
          <h2 id="checkpoints-heading">{route.name} checkpoints</h2>
          <span className="panel__hint">
            Weather sampled at the truck&rsquo;s estimated arrival time at each point.
          </span>
        </div>
        <CheckpointTable route={route} />
      </section>

      <RiskReference />
    </>
  )
}
