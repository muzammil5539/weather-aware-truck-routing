import type { Checkpoint, Route, Trip } from '../api/types'

export function checkpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    index: 0,
    lat: 39.7,
    lon: -105.0,
    distance_miles: 0,
    segment_miles: 25,
    eta: '2026-01-15T12:00:00+00:00',
    weather: {
      time: '2026-01-15T12:00:00+00:00',
      temperature_f: 41,
      wind_mph: 12,
      gust_mph: 20,
      rain_in_hr: 0,
      snow_in_hr: 0,
      precipitation_in_hr: 0,
      weather_code: 0,
    },
    risk_level: 'low',
    risk_score: 0,
    wind_level: 'low',
    rain_level: 'low',
    snow_level: 'low',
    driver: 'wind',
    ...overrides,
  }
}

export function route(overrides: Partial<Route> = {}): Route {
  return {
    name: 'Route A',
    summary: 'I 70 / I 15',
    source: 'osrm',
    distance_miles: 520,
    duration_hours: 8.5,
    arrival_at: '2026-01-15T20:30:00+00:00',
    geometry: [
      [39.7, -105.0],
      [40.0, -107.0],
      [40.76, -111.89],
    ],
    rank: 1,
    is_recommended: true,
    average_risk: 0.4,
    worst_level: 'moderate',
    risk_miles: { no_travel: 0, severe: 0, high: 0, moderate: 120, low: 400 },
    warnings: [],
    checkpoints: [checkpoint(), checkpoint({ index: 1, distance_miles: 25 })],
    ...overrides,
  }
}

export function trip(overrides: Partial<Trip> = {}): Trip {
  return {
    id: 'a1b2c3d4-0000-4000-8000-000000000000',
    origin: { label: 'Denver, Colorado, United States', lat: 39.7392, lon: -104.9903 },
    destination: { label: 'Salt Lake City, Utah, United States', lat: 40.7608, lon: -111.891 },
    departure_at: '2026-01-15T12:00:00+00:00',
    load_lb: 42000,
    checkpoint_interval_miles: 25,
    recommended_route: 'Route A',
    routes: [route(), route({ name: 'Route B', rank: 2, is_recommended: false })],
    heatmap: {
      anchor: '2026-01-15T12:00:00+00:00',
      hours: Array.from({ length: 48 }, (_, h) =>
        new Date(Date.UTC(2026, 0, 15, 12 + h)).toISOString(),
      ),
      points: [
        [39.7, -105.0],
        [40.5, -109.0],
      ],
      risk: [Array(48).fill(0), Array(48).fill(2)],
      wind_mph: [Array(48).fill(10), Array(48).fill(36)],
      rain_in_hr: [Array(48).fill(0), Array(48).fill(0)],
      snow_in_hr: [Array(48).fill(0), Array(48).fill(0)],
    },
    created_at: '2026-01-15T11:00:00+00:00',
    ...overrides,
  }
}
