import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import type { Trip, TripRequest } from '../api/types'
import { EmptyNotice, ErrorNotice, LoadingPanel } from '../components/Feedback'
import { RouteList } from '../components/RouteList'
import { TripForm } from '../components/TripForm'
import { TripView } from './TripView'

export function PlanPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()

  const [trip, setTrip] = useState<Trip | null>(null)
  // A trip id in the URL means we start out loading that trip.
  const [pending, setPending] = useState(Boolean(tripId))
  const [error, setError] = useState<ApiError | null>(null)
  const [selectedRouteName, setSelectedRouteName] = useState('')
  const [heatHour, setHeatHour] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [lastRequest, setLastRequest] = useState<TripRequest | null>(null)

  const adopt = useCallback((next: Trip) => {
    setTrip(next)
    setSelectedRouteName(next.recommended_route ?? next.routes[0]?.name ?? '')
    setHeatHour(0)
  }, [])

  // A trip id in the URL means someone opened a shared link.
  useEffect(() => {
    if (!tripId || trip?.id === tripId) return
    let cancelled = false
    api
      .getTrip(tripId)
      .then((loaded) => {
        if (!cancelled) adopt(loaded)
      })
      .catch((err: ApiError) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) setPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [tripId, trip?.id, adopt])

  const plan = useCallback(
    (request: TripRequest) => {
      setPending(true)
      setError(null)
      setLastRequest(request)
      api
        .planTrip(request)
        .then((created) => {
          adopt(created)
          // Put the trip in the URL so the plan can be shared or reloaded.
          navigate(`/trips/${created.id}`, { replace: false })
        })
        .catch((err: ApiError) => setError(err))
        .finally(() => setPending(false))
    },
    [adopt, navigate],
  )

  const selected = useMemo(
    () => trip?.routes.find((r) => r.name === selectedRouteName) ?? trip?.routes[0] ?? null,
    [trip, selectedRouteName],
  )

  return (
    <div className="app__main">
      <aside className="app__aside">
        <div>
          <h2 style={{ marginBottom: 4 }}>Plan a trip</h2>
          <p className="panel__hint" style={{ margin: 0 }}>
            Three routes, scored on the weather your truck will actually meet.
          </p>
        </div>

        <TripForm onSubmit={plan} pending={pending} fieldErrors={error?.fields} />

        {error && (
          <ErrorNotice
            message={error.message}
            onRetry={lastRequest && !error.isValidationError ? () => plan(lastRequest) : undefined}
          />
        )}

        {trip && selected && (
          <div>
            <h3 style={{ marginBottom: 8 }}>Route options</h3>
            <RouteList
              routes={trip.routes}
              selectedRouteName={selected.name}
              onSelect={setSelectedRouteName}
            />
          </div>
        )}
      </aside>

      <main className="app__content">
        {pending && !trip && <LoadingPanel label="Routing and sampling the forecast…" />}

        {!pending && !trip && !error && (
          <EmptyNotice>
            <p style={{ margin: 0, fontWeight: 600 }}>No trip planned yet.</p>
            <p style={{ margin: '6px 0 0' }}>
              Enter an origin, a destination, a departure time and your load weight to compare three
              routes.
            </p>
          </EmptyNotice>
        )}

        {trip && selected && (
          <TripView
            trip={trip}
            route={selected}
            onSelectRoute={setSelectedRouteName}
            heatHour={heatHour}
            onHeatHourChange={setHeatHour}
            showHeatmap={showHeatmap}
            onShowHeatmapChange={setShowHeatmap}
          />
        )}
      </main>
    </div>
  )
}
