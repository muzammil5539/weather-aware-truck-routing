import { useId, useState } from 'react'
import type { Place, TripRequest } from '../api/types'
import { nextHour, toLocalInputValue } from '../lib/format'
import { PlaceInput } from './PlaceInput'

const INTERVALS = [10, 25, 50] as const
const MAX_LOAD_LB = 200_000

interface Props {
  onSubmit: (request: TripRequest) => void
  pending: boolean
  fieldErrors?: Record<string, string[]>
}

interface Side {
  text: string
  place: Place | null
}

export function TripForm({ onSubmit, pending, fieldErrors = {} }: Props) {
  const loadId = useId()
  const departureId = useId()
  const intervalId = useId()

  const [origin, setOrigin] = useState<Side>({ text: '', place: null })
  const [destination, setDestination] = useState<Side>({ text: '', place: null })
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextHour()))
  const [loadLb, setLoadLb] = useState('42000')
  const [interval, setInterval] = useState<number>(25)
  const [errors, setErrors] = useState<Record<string, string>>({})

  function validate(): Record<string, string> {
    const next: Record<string, string> = {}
    if (!origin.text.trim()) next.origin = 'Enter a starting point.'
    if (!destination.text.trim()) next.destination = 'Enter a destination.'
    else if (origin.text.trim().toLowerCase() === destination.text.trim().toLowerCase())
      next.destination = 'Destination must differ from the origin.'
    if (!departure) next.departure_at = 'Choose a departure date and time.'
    const load = Number(loadLb)
    if (!loadLb.trim() || Number.isNaN(load)) next.load_lb = 'Enter the load weight in pounds.'
    else if (load < 0) next.load_lb = 'Load weight cannot be negative.'
    else if (load > MAX_LOAD_LB)
      next.load_lb = `Load weight must be ${MAX_LOAD_LB.toLocaleString()} lb or less.`
    return next
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length > 0) return

    onSubmit({
      origin: origin.text.trim(),
      destination: destination.text.trim(),
      departure_at: new Date(departure).toISOString(),
      load_lb: Number(loadLb),
      checkpoint_interval_miles: interval,
      ...(origin.place && { origin_lat: origin.place.lat, origin_lon: origin.place.lon }),
      ...(destination.place && {
        destination_lat: destination.place.lat,
        destination_lon: destination.place.lon,
      }),
    })
  }

  const errorFor = (name: string) => errors[name] ?? fieldErrors[name]?.[0]

  return (
    <form className="form" onSubmit={handleSubmit} noValidate aria-label="Plan a trip">
      <PlaceInput
        label="Origin"
        value={origin.text}
        error={errorFor('origin')}
        onChange={(text, place) => setOrigin({ text, place })}
      />
      <PlaceInput
        label="Destination"
        value={destination.text}
        error={errorFor('destination')}
        onChange={(text, place) => setDestination({ text, place })}
      />

      <div className={`field${errorFor('departure_at') ? ' field--invalid' : ''}`}>
        <label htmlFor={departureId}>Departure</label>
        <input
          id={departureId}
          type="datetime-local"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          aria-invalid={Boolean(errorFor('departure_at'))}
        />
        {errorFor('departure_at') && (
          <span className="field__error">{errorFor('departure_at')}</span>
        )}
      </div>

      <div className="form__row">
        <div className={`field${errorFor('load_lb') ? ' field--invalid' : ''}`}>
          <label htmlFor={loadId}>Load weight (lb)</label>
          <input
            id={loadId}
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD_LB}
            step={500}
            value={loadLb}
            onChange={(e) => setLoadLb(e.target.value)}
            aria-invalid={Boolean(errorFor('load_lb'))}
          />
          {errorFor('load_lb') && <span className="field__error">{errorFor('load_lb')}</span>}
        </div>

        <div className="field">
          <label htmlFor={intervalId}>Checkpoints every</label>
          <select
            id={intervalId}
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
          >
            {INTERVALS.map((miles) => (
              <option key={miles} value={miles}>
                {miles} miles
              </option>
            ))}
          </select>
        </div>
      </div>

      <button type="submit" className="button" disabled={pending}>
        {pending ? (
          <>
            <span className="spinner" aria-hidden="true" /> Checking the weather…
          </>
        ) : (
          'Find the safest route'
        )}
      </button>
    </form>
  )
}
