import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PlanPage } from './PlanPage'
import { ApiError } from '../api/client'
import { trip } from '../test/fixtures'

// Leaflet needs a real layout engine, which jsdom does not have. The map is
// covered by its own behaviour; here we only care about the page wiring.
vi.mock('../components/TripMap', () => ({
  TripMap: ({ selectedRouteName }: { selectedRouteName: string }) => (
    <div data-testid="map">map showing {selectedRouteName}</div>
  ),
}))

const planTrip = vi.fn()
const getTrip = vi.fn()
vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    api: {
      planTrip: (...args: unknown[]) => planTrip(...args),
      getTrip: (...args: unknown[]) => getTrip(...args),
      searchPlaces: vi.fn().mockResolvedValue([]),
    },
  }
})

function renderAt(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<PlanPage />} />
        <Route path="/trips/:tripId" element={<PlanPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function submitForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/origin/i), 'Denver, CO')
  await user.type(screen.getByLabelText(/destination/i), 'Salt Lake City, UT')
  await user.click(screen.getByRole('button', { name: /find the safest route/i }))
}

beforeEach(() => {
  planTrip.mockReset()
  getTrip.mockReset()
})

describe('PlanPage', () => {
  it('invites the driver to plan a trip before anything is submitted', () => {
    renderAt()
    expect(screen.getByText(/no trip planned yet/i)).toBeInTheDocument()
  })

  it('plans a trip and shows routes, map and checkpoints', async () => {
    planTrip.mockResolvedValue(trip())
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Denver → Salt Lake City/ })).toBeInTheDocument()
    expect(screen.getByText('Recommended')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Route A checkpoints/ })).toBeInTheDocument()
  })

  it('opens on the recommended route', async () => {
    planTrip.mockResolvedValue(trip({ recommended_route: 'Route B' }))
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)
    expect(await screen.findByTestId('map')).toHaveTextContent('map showing Route B')
  })

  it('switches the map and table when another route is chosen', async () => {
    planTrip.mockResolvedValue(trip())
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    await screen.findByTestId('map')
    await user.click(screen.getByRole('button', { name: /Route B/ }))

    expect(screen.getByTestId('map')).toHaveTextContent('map showing Route B')
    expect(screen.getByRole('heading', { name: /Route B checkpoints/ })).toBeInTheDocument()
  })

  it('shows a 0–48 hour forecast slider', async () => {
    planTrip.mockResolvedValue(trip())
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    const slider = await screen.findByRole('slider')
    expect(slider).toHaveAttribute('max', '47')
  })

  it('reports an upstream failure without losing the form', async () => {
    planTrip.mockRejectedValue(new ApiError('No drivable route connects those two places.', 422))
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/no drivable route/i)
    expect(screen.getByRole('button', { name: /find the safest route/i })).toBeEnabled()
  })

  it('retries the same request after a transient failure', async () => {
    planTrip.mockRejectedValueOnce(new ApiError('The server is having trouble.', 502))
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    planTrip.mockResolvedValue(trip())
    await user.click(await screen.findByRole('button', { name: /try again/i }))

    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(planTrip).toHaveBeenCalledTimes(2)
    expect(planTrip.mock.calls[0][0]).toEqual(planTrip.mock.calls[1][0])
  })

  it('does not offer a retry for a validation error', async () => {
    planTrip.mockRejectedValue(
      new ApiError('load_lb: Too heavy.', 400, { load_lb: ['Too heavy.'] }),
    )
    const user = userEvent.setup()
    renderAt()
    await submitForm(user)

    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })

  it('loads a shared trip straight from its URL', async () => {
    getTrip.mockResolvedValue(trip())
    renderAt('/trips/a1b2c3d4-0000-4000-8000-000000000000')

    expect(await screen.findByTestId('map')).toBeInTheDocument()
    expect(getTrip).toHaveBeenCalledWith('a1b2c3d4-0000-4000-8000-000000000000')
  })

  it('explains a shared link that no longer resolves', async () => {
    getTrip.mockRejectedValue(new ApiError('That trip no longer exists.', 404))
    renderAt('/trips/missing')
    expect(await screen.findByRole('alert')).toHaveTextContent(/no longer exists/i)
  })
})
