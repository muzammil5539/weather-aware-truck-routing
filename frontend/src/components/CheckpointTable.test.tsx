import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { CheckpointTable } from './CheckpointTable'
import { checkpoint, route } from '../test/fixtures'

describe('CheckpointTable', () => {
  const subject = route({
    checkpoints: [
      checkpoint({ index: 0, distance_miles: 0 }),
      checkpoint({
        index: 1,
        distance_miles: 25,
        risk_level: 'severe',
        driver: 'load',
        weather: {
          time: '2026-01-15T13:00:00+00:00',
          temperature_f: 28,
          wind_mph: 47,
          gust_mph: 60,
          rain_in_hr: 0,
          snow_in_hr: 1.4,
          precipitation_in_hr: 1.4,
          weather_code: 73,
        },
      }),
    ],
  })

  it('renders one row per checkpoint', () => {
    render(<CheckpointTable route={subject} />)
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2
  })

  it('shows the readings the risk table is built on', () => {
    render(<CheckpointTable route={subject} />)
    const row = screen.getByRole('row', { name: /47 mph/ })
    expect(within(row).getByText('1.40 in/hr')).toBeInTheDocument()
    expect(within(row).getByText('28°F')).toBeInTheDocument()
    expect(within(row).getByText('Severe')).toBeInTheDocument()
  })

  it('names what drove the risk level', () => {
    render(<CheckpointTable route={subject} />)
    expect(screen.getByText('Load rule')).toBeInTheDocument()
  })

  it('shows a dash when a checkpoint has no forecast', () => {
    const noWeather = route({ checkpoints: [checkpoint({ weather: null })] })
    render(<CheckpointTable route={noWeather} />)
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
  })
})
