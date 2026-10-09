import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TripForm } from './TripForm'

vi.mock('../api/client', () => ({
  api: { searchPlaces: vi.fn().mockResolvedValue([]) },
  ApiError: class extends Error {},
}))

function setup(props: Partial<Parameters<typeof TripForm>[0]> = {}) {
  const onSubmit = vi.fn()
  render(<TripForm onSubmit={onSubmit} pending={false} {...props} />)
  return { onSubmit, user: userEvent.setup() }
}

describe('TripForm', () => {
  it('submits the four required inputs from the brief', async () => {
    const { onSubmit, user } = setup()

    await user.type(screen.getByLabelText(/origin/i), 'Denver, CO')
    await user.type(screen.getByLabelText(/destination/i), 'Salt Lake City, UT')
    await user.clear(screen.getByLabelText(/load weight/i))
    await user.type(screen.getByLabelText(/load weight/i), '38000')
    await user.click(screen.getByRole('button', { name: /find the safest route/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0][0]
    expect(payload.origin).toBe('Denver, CO')
    expect(payload.destination).toBe('Salt Lake City, UT')
    expect(payload.load_lb).toBe(38000)
    expect(payload.departure_at).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    expect(payload.checkpoint_interval_miles).toBe(25)
  })

  it('offers exactly the 10 / 25 / 50 mile checkpoint intervals', () => {
    setup()
    const options = screen.getAllByRole('option') as HTMLOptionElement[]
    expect(options.map((o) => o.value)).toEqual(['10', '25', '50'])
  })

  it('sends the chosen checkpoint interval', async () => {
    const { onSubmit, user } = setup()
    await user.type(screen.getByLabelText(/origin/i), 'Denver')
    await user.type(screen.getByLabelText(/destination/i), 'Moab')
    await user.selectOptions(screen.getByLabelText(/checkpoints every/i), '10')
    await user.click(screen.getByRole('button', { name: /find the safest route/i }))
    await waitFor(() => expect(onSubmit.mock.calls[0][0].checkpoint_interval_miles).toBe(10))
  })

  it('blocks submission and explains why when fields are empty', async () => {
    const { onSubmit, user } = setup()
    await user.clear(screen.getByLabelText(/load weight/i))
    await user.click(screen.getByRole('button', { name: /find the safest route/i }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText(/enter a starting point/i)).toBeInTheDocument()
    expect(screen.getByText(/enter a destination/i)).toBeInTheDocument()
    expect(screen.getByText(/enter the load weight/i)).toBeInTheDocument()
  })

  it('rejects a negative load', async () => {
    const { onSubmit, user } = setup()
    await user.type(screen.getByLabelText(/origin/i), 'Denver')
    await user.type(screen.getByLabelText(/destination/i), 'Moab')
    await user.clear(screen.getByLabelText(/load weight/i))
    await user.type(screen.getByLabelText(/load weight/i), '-500')
    await user.click(screen.getByRole('button', { name: /find the safest route/i }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText(/cannot be negative/i)).toBeInTheDocument()
  })

  it('rejects a destination identical to the origin', async () => {
    const { onSubmit, user } = setup()
    await user.type(screen.getByLabelText(/origin/i), 'Denver, CO')
    await user.type(screen.getByLabelText(/destination/i), 'denver, co')
    await user.click(screen.getByRole('button', { name: /find the safest route/i }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText(/must differ from the origin/i)).toBeInTheDocument()
  })

  it('shows server-side field errors', () => {
    setup({ fieldErrors: { load_lb: ['Ensure this value is less than or equal to 200000.'] } })
    expect(screen.getByText(/less than or equal to 200000/i)).toBeInTheDocument()
  })

  it('disables the button while a plan is in flight', () => {
    setup({ pending: true })
    expect(screen.getByRole('button', { name: /checking the weather/i })).toBeDisabled()
  })
})
