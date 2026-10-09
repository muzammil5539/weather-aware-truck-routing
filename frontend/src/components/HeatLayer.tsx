import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'
import { RISK_COLOR, RISK_ORDER } from '../lib/risk'

interface Props {
  points: [number, number][]
  /** Risk score 0–4 for each point, for the hour being shown. */
  scores: number[]
  opacity?: number
}

/**
 * A canvas heat layer for the trip corridor.
 *
 * Each corridor point is painted as a radial gradient in the colour of its own
 * risk level, so colour means risk and alpha means proximity. Points are drawn
 * worst-last, which keeps a Severe pocket visible instead of being averaged
 * away by the calm weather around it. An additive intensity heatmap would blend
 * two adjacent Low points into a High-looking blob, which would be a lie.
 *
 * ponytail: ~70 lines of canvas instead of leaflet.heat, which is unmaintained,
 * ships no types, and only does the additive blend we do not want here.
 */
export function HeatLayer({ points, scores, opacity = 0.5 }: Props) {
  const map = useMap()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const frameRef = useRef(0)
  const dataRef = useRef({ points, scores, opacity })

  useEffect(() => {
    const canvas = L.DomUtil.create('canvas', 'leaflet-zoom-animated') as HTMLCanvasElement
    canvas.style.pointerEvents = 'none'
    canvasRef.current = canvas
    map.getPanes().overlayPane.appendChild(canvas)

    const draw = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const { points: pts, scores: values, opacity: alpha } = dataRef.current

      const size = map.getSize()
      const dpr = window.devicePixelRatio || 1
      if (canvas.width !== size.x * dpr || canvas.height !== size.y * dpr) {
        canvas.width = size.x * dpr
        canvas.height = size.y * dpr
        canvas.style.width = `${size.x}px`
        canvas.style.height = `${size.y}px`
      }
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]))

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, size.x, size.y)

      // Radius grows with zoom so the corridor stays a band rather than dots.
      const radius = Math.max(26, Math.min(130, 2.6 * 2 ** (map.getZoom() - 5)))

      // Worst risk last, so it paints over the calm weather around it. Calm
      // stretches are drawn too, faintly: an empty map would read as "no data"
      // rather than "nothing to worry about".
      const order = pts.map((_, i) => i).sort((a, b) => (values[a] ?? 0) - (values[b] ?? 0))

      for (const i of order) {
        const point = map.latLngToContainerPoint(pts[i])
        if (
          point.x < -radius ||
          point.y < -radius ||
          point.x > size.x + radius ||
          point.y > size.y + radius
        ) {
          continue
        }
        const score = values[i] ?? 0
        const level = RISK_ORDER[Math.min(RISK_ORDER.length - 1, Math.round(score))]
        const levelAlpha = score === 0 ? alpha * 0.35 : alpha
        const gradient = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius)
        gradient.addColorStop(0, hexToRgba(RISK_COLOR[level], levelAlpha))
        gradient.addColorStop(0.55, hexToRgba(RISK_COLOR[level], levelAlpha * 0.55))
        gradient.addColorStop(1, hexToRgba(RISK_COLOR[level], 0))
        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    const schedule = () => {
      cancelAnimationFrame(frameRef.current)
      frameRef.current = requestAnimationFrame(draw)
    }

    map.on('move zoom resize viewreset zoomanim', schedule)
    schedule()

    return () => {
      map.off('move zoom resize viewreset zoomanim', schedule)
      cancelAnimationFrame(frameRef.current)
      canvas.remove()
      canvasRef.current = null
    }
  }, [map])

  // Redraw when the hour slider moves, without rebuilding the canvas.
  useEffect(() => {
    dataRef.current = { points, scores, opacity }
    if (!canvasRef.current) return
    map.fire('viewreset')
  }, [map, points, scores, opacity])

  return null
}

function hexToRgba(hex: string, alpha: number): string {
  const value = parseInt(hex.slice(1), 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}
