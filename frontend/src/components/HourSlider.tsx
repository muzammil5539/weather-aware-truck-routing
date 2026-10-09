import { useEffect, useId, useRef, useState } from 'react'
import { formatHour } from '../lib/format'

interface Props {
  hours: string[]
  value: number
  onChange: (hour: number) => void
}

/** 0–48 hour forecast scrubber, with play/pause for the whole window. */
export function HourSlider({ hours, value, onChange }: Props) {
  const id = useId()
  const [playing, setPlaying] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  useEffect(() => {
    if (!playing) return
    timer.current = setInterval(() => {
      onChange((value + 1) % hours.length)
    }, 420)
    return () => clearInterval(timer.current)
  }, [playing, value, hours.length, onChange])

  if (hours.length === 0) return null
  const current = hours[Math.min(value, hours.length - 1)]

  return (
    <div className="slider">
      <div className="slider__row">
        <button
          type="button"
          className="button button--ghost"
          style={{ minWidth: 76 }}
          onClick={() => setPlaying((p) => !p)}
          aria-pressed={playing}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <label htmlFor={id} className="visually-hidden">
          Forecast hour
        </label>
        <input
          id={id}
          type="range"
          min={0}
          max={hours.length - 1}
          step={1}
          value={value}
          onChange={(e) => {
            setPlaying(false)
            onChange(Number(e.target.value))
          }}
          aria-valuetext={`${value} hours from departure, ${formatHour(current)}`}
        />
        <span className="slider__time num" role="status">
          +{value}h · {formatHour(current)}
        </span>
      </div>
      <div className="slider__ticks" aria-hidden="true">
        <span>Departure</span>
        <span>+12h</span>
        <span>+24h</span>
        <span>+36h</span>
        <span>+{hours.length - 1}h</span>
      </div>
    </div>
  )
}
