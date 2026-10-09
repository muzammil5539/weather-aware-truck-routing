import type { ApiErrorBody, Place, Trip, TripRequest } from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

// A production build with no API origin compiled in will aim every request at
// the site's own origin, where there is no API. That fails as a bare 404 with
// nothing to explain it, so say so once, loudly, in the console.
if (!BASE_URL && typeof window !== 'undefined' && !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname)) {
  console.warn(
    '[truck-routing] VITE_API_BASE_URL is not set, so API requests are going to ' +
      `${window.location.origin}/api/..., which serves no API. Set it to the deployed ` +
      'Django API origin and rebuild - Vite inlines it at build time.',
  )
}

export class ApiError extends Error {
  /** Per-field messages from a 400, keyed by form field name. */
  readonly fields: Record<string, string[]>
  readonly status: number

  constructor(message: string, status: number, fields: Record<string, string[]> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
  }

  /** True when the server rejected specific form fields, so retrying as-is is pointless. */
  get isValidationError(): boolean {
    return Object.keys(this.fields).length > 0
  }
}

function readableError(status: number, body: ApiErrorBody, path: string): ApiError {
  const error = body.error
  if (error?.fields) {
    const first = Object.entries(error.fields)[0]
    const message = first ? `${first[0]}: ${[first[1]].flat().join(' ')}` : 'Please check the form.'
    return new ApiError(message, status, error.fields)
  }
  if (error?.detail) return new ApiError(error.detail, status)
  if (status === 404) {
    // Only a request for one specific trip can mean "that trip is gone". A 404
    // on any other path means the API itself is not where we are looking.
    const isSingleTrip = path.startsWith('/api/trips/') && path !== '/api/trips/'
    return new ApiError(
      isSingleTrip
        ? 'That trip no longer exists.'
        : 'Could not reach the routing service. It may still be starting up.',
      status,
    )
  }
  if (status >= 500) return new ApiError('The server is having trouble. Please try again.', status)
  return new ApiError('Something went wrong. Please try again.', status)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError('Could not reach the server. Check your connection.', 0)
  }

  if (!response.ok) {
    let body: ApiErrorBody = {}
    try {
      body = (await response.json()) as ApiErrorBody
    } catch {
      /* a non-JSON error body is fine; fall through to the generic message */
    }
    throw readableError(response.status, body, path)
  }

  return (await response.json()) as T
}

export const api = {
  planTrip: (payload: TripRequest) =>
    request<Trip>('/api/trips/', { method: 'POST', body: JSON.stringify(payload) }),

  getTrip: (id: string) => request<Trip>(`/api/trips/${id}/`),

  searchPlaces: (query: string, signal?: AbortSignal) =>
    request<{ results: Place[] }>(`/api/geocode/?q=${encodeURIComponent(query)}`, { signal }).then(
      (body) => body.results,
    ),
}
