import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { HourSlider } from './HourSlider'

const HOURS = Array.from({ length: 48 }, (_, h) =>
  new Date(Date.UTC(2026, 0, 15, 12 + h)).toISOString(),
)

describe('HourSlider', () => {
  it('spans the full 0–48 hour forecast window', () => {
    render(<HourSlider hours={HOURS} value={0} onChange={() => {}} />)
    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '47')
  })

  it('reports the hour the user scrubs to', async () => {
    const onChange = vi.fn()
    render(<HourSlider hours={HOURS} value={0} onChange={onChange} />)
    // jsdom has no native range-drag, so drive the change event directly.
    fireEvent.change(screen.getByRole('slider'), { target: { value: '7' } })
    expect(onChange).toHaveBeenCalledWith(7)
  })

  it('shows the offset from departure', () => {
    render(<HourSlider hours={HOURS} value={12} onChange={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('+12h')
  })

  it('advances automatically while playing, and stops when paused', async () => {
    vi.useFakeTimers()
    try {
      const onChange = vi.fn()
      render(<HourSlider hours={HOURS} value={3} onChange={onChange} />)

      fireEvent.click(screen.getByRole('button', { name: 'Play' }))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500)
      })
      expect(onChange).toHaveBeenCalledWith(4)

      fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
      onChange.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })
      expect(onChange).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('wraps back to departure at the end of the window', async () => {
    vi.useFakeTimers()
    try {
      const onChange = vi.fn()
      render(<HourSlider hours={HOURS} value={47} onChange={onChange} />)
      fireEvent.click(screen.getByRole('button', { name: 'Play' }))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500)
      })
      expect(onChange).toHaveBeenCalledWith(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops playing when the user scrubs manually', async () => {
    vi.useFakeTimers()
    try {
      const onChange = vi.fn()
      render(<HourSlider hours={HOURS} value={3} onChange={onChange} />)
      fireEvent.click(screen.getByRole('button', { name: 'Play' }))
      fireEvent.change(screen.getByRole('slider'), { target: { value: '20' } })
      expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders nothing without forecast hours', () => {
    const { container } = render(<HourSlider hours={[]} value={0} onChange={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
