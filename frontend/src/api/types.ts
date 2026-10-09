export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface WeatherReading {
  time: string
  temperature_f: number
  wind_mph: number
  gust_mph: number
  rain_in_hr: number
  snow_in_hr: number
  precipitation_in_hr: number
  weather_code: number
}

export interface Checkpoint {
  index: number
  lat: number
  lon: number
  distance_miles: number
  segment_miles: number
  eta: string
  weather: WeatherReading | null
  risk_level: RiskLevel
  risk_score: number
  wind_level: RiskLevel
  rain_level: RiskLevel
  snow_level: RiskLevel
  driver: 'wind' | 'rain' | 'snow' | 'load'
}

export interface RiskMiles {
  no_travel: number
  severe: number
  high: number
  moderate: number
  low: number
}

export interface Route {
  name: string
  summary: string
  source?: 'osrm' | 'detour'
  distance_miles: number
  duration_hours: number
  arrival_at: string
  geometry: [number, number][]
  rank: number
  is_recommended: boolean
  average_risk: number
  worst_level: RiskLevel
  risk_miles: RiskMiles
  warnings: string[]
  checkpoints: Checkpoint[]
}

export interface Heatmap {
  anchor: string
  hours: string[]
  points: [number, number][]
  risk: number[][]
  wind_mph: number[][]
  rain_in_hr: number[][]
  snow_in_hr: number[][]
}

export interface Trip {
  id: string
  origin: Place
  destination: Place
  departure_at: string
  load_lb: number
  checkpoint_interval_miles: number
  recommended_route: string | null
  routes: Route[]
  heatmap: Heatmap
  created_at: string
}

export interface TripRequest {
  origin: string
  destination: string
  departure_at: string
  load_lb: number
  checkpoint_interval_miles: number
  origin_lat?: number
  origin_lon?: number
  destination_lat?: number
  destination_lon?: number
}

export interface ApiErrorBody {
  error?: {
    type?: string
    provider?: string
    detail?: string
    fields?: Record<string, string[]>
  }
}
