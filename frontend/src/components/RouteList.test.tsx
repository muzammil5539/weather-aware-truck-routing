import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouteList } from './RouteList'
import { route } from '../test/fixtures'

const ROUTES = [
  route({ name: 'Route A', rank: 1, is_recommended: true }),
  route({
    name: 'Route B',
    rank: 2,
    is_recommended: false,
    worst_level: 'severe',
    risk_miles: { no_travel: 0, severe: 80, high: 40, moderate: 0, low: 400 },
    warnings: ['80 mi of Severe conditions.'],
  }),
  route({
    name: 'Route C',
    rank: 3,
    is_recommended: false,
    source: 'detour',
    worst_level: 'no_travel',
    risk_miles: { no_travel: 30, severe: 50, high: 0, moderate: 0, low: 500 },
    warnings: ['30 mi fall under No Travel conditions for this load.'],
  }),
]

describe('RouteList', () => {
  it('lists every route option', () => {
    render(<RouteList routes={ROUTES} selectedRouteName="Route A" onSelect={() => {}} />)
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })

  it('badges only the recommended route', () => {
    render(<RouteList routes={ROUTES} selectedRouteName="Route A" onSelect={() => {}} />)
    expect(screen.getAllByText('Recommended')).toHaveLength(1)
  })

  it('marks the selected route as pressed', () => {
    render(<RouteList routes={ROUTES} selectedRouteName="Route B" onSelect={() => {}} />)
    expect(screen.getByRole('button', { pressed: true })).toHaveTextContent('Route B')
  })

  it('reports the clicked route', async () => {
    const onSelect = vi.fn()
    render(<RouteList routes={ROUTES} selectedRouteName="Route A" onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Route C/ }))
    expect(onSelect).toHaveBeenCalledWith('Route C')
  })

  it('shows distance, drive time and average risk', () => {
    render(<RouteList routes={[ROUTES[0]]} selectedRouteName="Route A" onSelect={() => {}} />)
    expect(screen.getByText('520 mi')).toBeInTheDocument()
    expect(screen.getByText('8 hr 30 min')).toBeInTheDocument()
    expect(screen.getByText('0.40')).toBeInTheDocument()
  })

  it('surfaces No Travel and Severe warnings', () => {
    render(<RouteList routes={ROUTES} selectedRouteName="Route A" onSelect={() => {}} />)
    expect(screen.getByText(/30 mi fall under No Travel/)).toBeInTheDocument()
    expect(screen.getByText(/80 mi of Severe conditions/)).toBeInTheDocument()
  })

  it('describes the risk mix for screen readers', () => {
    render(<RouteList routes={[ROUTES[2]]} selectedRouteName="Route C" onSelect={() => {}} />)
    expect(
      screen.getByRole('img', { name: /30 miles No Travel, 50 miles Severe/ }),
    ).toBeInTheDocument()
  })

  it('notes when a route came from an alternate corridor', () => {
    render(<RouteList routes={[ROUTES[2]]} selectedRouteName="Route C" onSelect={() => {}} />)
    expect(screen.getByText(/alternate corridor/)).toBeInTheDocument()
  })
})
