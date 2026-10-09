import type { ApiErrorBody, Place, Trip, TripRequest } from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

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

function readableError(status: number, body: ApiErrorBody): ApiError {
  const error = body.error
  if (error?.fields) {
    const first = Object.entries(error.fields)[0]
    const message = first ? `${first[0]}: ${[first[1]].flat().join(' ')}` : 'Please check the form.'
    return new ApiError(message, status, error.fields)
  }
  if (error?.detail) return new ApiError(error.detail, status)
  if (status === 404) return new ApiError('That trip no longer exists.', status)
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
    throw readableError(response.status, body)
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
