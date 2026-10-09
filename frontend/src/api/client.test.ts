import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './client'
import { trip } from '../test/fixtures'

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
  vi.stubGlobal('fetch', fn)
  return fn
}

beforeEach(() => vi.unstubAllGlobals())

describe('planTrip', () => {
  it('posts the request and returns the trip', async () => {
    const fetchMock = mockFetch(201, trip())
    const result = await api.planTrip({
      origin: 'Denver',
      destination: 'Salt Lake City',
      departure_at: '2026-01-15T12:00:00.000Z',
      load_lb: 42000,
      checkpoint_interval_miles: 25,
    })

    expect(result.id).toBe(trip().id)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/trips/')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body).load_lb).toBe(42000)
  })

  it('surfaces field errors from a 400 so the form can show them', async () => {
    mockFetch(400, { error: { type: 'validation_error', fields: { load_lb: ['Too heavy.'] } } })
    await expect(
      api.planTrip({
        origin: 'A',
        destination: 'B',
        departure_at: '2026-01-15T12:00:00.000Z',
        load_lb: 9e9,
        checkpoint_interval_miles: 25,
      }),
    ).rejects.toMatchObject({ status: 400, fields: { load_lb: ['Too heavy.'] } })
  })

  it('surfaces an upstream detail from a 422', async () => {
    mockFetch(422, {
      error: {
        type: 'upstream_error',
        provider: 'nominatim',
        detail: "Could not find 'Atlantis'.",
      },
    })
    await expect(api.getTrip('x')).rejects.toThrow("Could not find 'Atlantis'.")
  })

  it('gives a readable message for a server error', async () => {
    mockFetch(500, {})
    await expect(api.getTrip('x')).rejects.toThrow(/server is having trouble/i)
  })

  it('gives a readable message for a missing trip', async () => {
    mockFetch(404, {})
    await expect(api.getTrip('x')).rejects.toThrow(/no longer exists/i)
  })

  it('does not blame a missing trip when the API itself is not there', async () => {
    // A deploy with no VITE_API_BASE_URL aims POST /api/trips/ at the static
    // host, which 404s. That is not a missing trip.
    mockFetch(404, {})
    await expect(
      api.planTrip({
        origin: 'A',
        destination: 'B',
        departure_at: '2026-01-15T12:00:00.000Z',
        load_lb: 100,
        checkpoint_interval_miles: 25,
      }),
    ).rejects.toThrow(/could not reach the routing service/i)
  })

  it('survives a non-JSON error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('not json')
        },
      } as unknown as Response),
    )
    await expect(api.getTrip('x')).rejects.toBeInstanceOf(ApiError)
  })

  it('reports a network failure rather than throwing a raw TypeError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.getTrip('x')).rejects.toThrow(/could not reach the server/i)
  })
})

describe('searchPlaces', () => {
  it('encodes the query and unwraps results', async () => {
    const fetchMock = mockFetch(200, { results: [{ label: 'Denver, CO', lat: 39.7, lon: -105 }] })
    const results = await api.searchPlaces('Denver, CO')
    expect(results).toHaveLength(1)
    expect(fetchMock.mock.calls[0][0]).toContain('q=Denver%2C%20CO')
  })
})

describe('ApiError.isValidationError', () => {
  it('is true only when the server named specific fields', () => {
    expect(new ApiError('boom', 502).isValidationError).toBe(false)
    expect(new ApiError('bad', 400, { load_lb: ['Too heavy.'] }).isValidationError).toBe(true)
  })
})
