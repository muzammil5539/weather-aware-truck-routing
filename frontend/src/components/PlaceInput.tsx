import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Place } from '../api/types'
import { useDebounced } from '../hooks/useDebounced'

interface Props {
  label: string
  value: string
  error?: string
  onChange: (value: string, place: Place | null) => void
}

/**
 * Free-text place input with geocoder suggestions. Picking a suggestion pins
 * its coordinates so the backend does not have to guess the place again.
 */
export function PlaceInput({ label, value, error, onChange }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [suggestions, setSuggestions] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const justPicked = useRef(false)
  const query = useDebounced(value, 300)

  useEffect(() => {
    if (justPicked.current) {
      justPicked.current = false
      return
    }
    if (query.trim().length < 3) return
    const controller = new AbortController()
    api
      .searchPlaces(query, controller.signal)
      .then((results) => {
        setSuggestions(results)
        setActive(-1)
      })
      // A failed lookup must not break typing: the user can still submit the
      // raw text and let the backend geocode it.
      .catch(() => setSuggestions([]))
    return () => controller.abort()
  }, [query])

  function pick(place: Place) {
    justPicked.current = true
    onChange(place.label, place)
    setSuggestions([])
    setOpen(false)
    setActive(-1)
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const options = value.trim().length >= 3 ? suggestions : []
    if (!open || options.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % options.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1))
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault()
      pick(options[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  // Derived, not stored: a query too short to search shows nothing, without a
  // state update that would cascade another render.
  const visible = value.trim().length >= 3 ? suggestions : []
  const showList = open && visible.length > 0

  return (
    <div className={`field${error ? ' field--invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={value}
        autoComplete="off"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        placeholder="City, state or lat, lon"
        onChange={(e) => {
          onChange(e.target.value, null)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="suggestions" id={listId} role="listbox" aria-label={`${label} suggestions`}>
          {visible.map((place, i) => (
            <li key={`${place.lat},${place.lon}`} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(place)}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <span className="field__error" id={`${id}-error`}>
          {error}
        </span>
      )}
    </div>
  )
}
