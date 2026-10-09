import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { Checkpoint, Trip } from '../api/types'
import { formatDateTime, formatMiles } from '../lib/format'
import { DRIVER_LABEL, RISK_COLOR, RISK_LABEL } from '../lib/risk'
import { HeatLayer } from './HeatLayer'

// Leaflet's default marker icons are resolved against the stylesheet's URL,
// which a bundler rewrites; point them at the packaged assets explicitly.
const endpointIcon = (color: string) =>
  L.divIcon({
    className: '',
    html: `<span style="display:block;width:16px;height:16px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.35)"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  })

const ORIGIN_ICON = endpointIcon('#0b3c49')
const DESTINATION_ICON = endpointIcon('#c8651a')

/**
 * Wheel zoom starts off so scrolling the page over the map does not hijack it,
 * and switches on once the user clicks into the map. Leaving the pointer turns
 * it back off.
 */
function ClickToZoom() {
  const map = useMap()
  useEffect(() => {
    const enable = () => map.scrollWheelZoom.enable()
    const disable = () => map.scrollWheelZoom.disable()
    map.on('click focus', enable)
    map.on('mouseout', disable)
    return () => {
      map.off('click focus', enable)
      map.off('mouseout', disable)
    }
  }, [map])
  return null
}

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length < 2) return
    map.fitBounds(L.latLngBounds(positions), { padding: [36, 36] })
  }, [map, positions])
  return null
}

interface Props {
  trip: Trip
  selectedRouteName: string
  onSelectRoute: (name: string) => void
  heatHour: number
  showHeatmap: boolean
}

export function TripMap({ trip, selectedRouteName, onSelectRoute, heatHour, showHeatmap }: Props) {
  const selected = trip.routes.find((r) => r.name === selectedRouteName) ?? trip.routes[0]

  const allPositions = useMemo(() => trip.routes.flatMap((route) => route.geometry), [trip.routes])

  const heatScores = useMemo(() => {
    const grid = trip.heatmap?.risk ?? []
    const hour = Math.min(heatHour, (trip.heatmap?.hours?.length ?? 1) - 1)
    return grid.map((row) => row[hour] ?? 0)
  }, [trip.heatmap, heatHour])

  if (!selected) return null

  return (
    <div className="map">
      <MapContainer center={[39.5, -98.35]} zoom={4} scrollWheelZoom={false} preferCanvas>
        <ClickToZoom />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={18}
        />
        <FitBounds positions={allPositions} />

        {showHeatmap && trip.heatmap?.points?.length > 0 && (
          <HeatLayer points={trip.heatmap.points} scores={heatScores} />
        )}

        {/* Unselected routes first, so the selected one draws on top. */}
        {trip.routes
          .filter((route) => route.name !== selected.name)
          .map((route) => (
            <Polyline
              key={route.name}
              positions={route.geometry}
              pathOptions={{ color: '#5a6866', weight: 4, opacity: 0.45, dashArray: '6 7' }}
              eventHandlers={{ click: () => onSelectRoute(route.name) }}
            >
              <Popup>
                <strong>{route.name}</strong>
                <br />
                {formatMiles(route.distance_miles)} · {RISK_LABEL[route.worst_level]} worst case
              </Popup>
            </Polyline>
          ))}

        <Polyline
          positions={selected.geometry}
          pathOptions={{ color: '#0b3c49', weight: 6, opacity: 0.95 }}
        />

        {selected.checkpoints.map((checkpoint) => (
          <CircleMarker
            key={checkpoint.index}
            center={[checkpoint.lat, checkpoint.lon]}
            radius={6}
            pathOptions={{
              color: '#ffffff',
              weight: 2,
              fillColor: RISK_COLOR[checkpoint.risk_level],
              fillOpacity: 1,
            }}
          >
            <Popup>
              <CheckpointPopup checkpoint={checkpoint} />
            </Popup>
          </CircleMarker>
        ))}

        <Marker position={[trip.origin.lat, trip.origin.lon]} icon={ORIGIN_ICON}>
          <Popup>
            <strong>Origin</strong>
            <br />
            {trip.origin.label}
          </Popup>
        </Marker>
        <Marker position={[trip.destination.lat, trip.destination.lon]} icon={DESTINATION_ICON}>
          <Popup>
            <strong>Destination</strong>
            <br />
            {trip.destination.label}
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  )
}

function CheckpointPopup({ checkpoint }: { checkpoint: Checkpoint }) {
  const weather = checkpoint.weather
  return (
    <div>
      <strong>
        Checkpoint {checkpoint.index} · {formatMiles(checkpoint.distance_miles)}
      </strong>
      <br />
      <span
        className="pill"
        style={{
          background: RISK_COLOR[checkpoint.risk_level],
          marginTop: 4,
          display: 'inline-flex',
        }}
      >
        {RISK_LABEL[checkpoint.risk_level]}
      </span>
      <dl>
        <dt>ETA</dt>
        <dd>{formatDateTime(checkpoint.eta)}</dd>
        <dt>Wind</dt>
        <dd>{weather ? `${weather.wind_mph.toFixed(0)} mph` : '—'}</dd>
        <dt>Rain</dt>
        <dd>{weather ? `${weather.rain_in_hr.toFixed(2)} in/hr` : '—'}</dd>
        <dt>Snow</dt>
        <dd>{weather ? `${weather.snow_in_hr.toFixed(2)} in/hr` : '—'}</dd>
        <dt>Temp</dt>
        <dd>{weather ? `${weather.temperature_f.toFixed(0)}°F` : '—'}</dd>
        <dt>Driven by</dt>
        <dd>{DRIVER_LABEL[checkpoint.driver] ?? checkpoint.driver}</dd>
      </dl>
    </div>
  )
}
