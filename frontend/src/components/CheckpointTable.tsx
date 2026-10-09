import type { Route } from '../api/types'
import { formatDateTime } from '../lib/format'
import { DRIVER_LABEL } from '../lib/risk'
import { RiskPill } from './RiskPill'

export function CheckpointTable({ route }: { route: Route }) {
  return (
    <div className="tablewrap">
      <table className="checkpoints">
        <caption className="visually-hidden">
          Weather and risk at each checkpoint along {route.name}
        </caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Risk</th>
            <th scope="col">Mile</th>
            <th scope="col">ETA</th>
            <th scope="col">Wind</th>
            <th scope="col">Rain</th>
            <th scope="col">Snow</th>
            <th scope="col">Temp</th>
            <th scope="col">Driven by</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((checkpoint) => (
            <tr key={checkpoint.index}>
              <th scope="row" className="num">
                {checkpoint.index}
              </th>
              <td>
                <RiskPill level={checkpoint.risk_level} />
              </td>
              <td className="num">{Math.round(checkpoint.distance_miles)}</td>
              <td className="num">{formatDateTime(checkpoint.eta)}</td>
              <td className="num">
                {checkpoint.weather ? `${checkpoint.weather.wind_mph.toFixed(0)} mph` : '—'}
              </td>
              <td className="num">
                {checkpoint.weather ? `${checkpoint.weather.rain_in_hr.toFixed(2)} in/hr` : '—'}
              </td>
              <td className="num">
                {checkpoint.weather ? `${checkpoint.weather.snow_in_hr.toFixed(2)} in/hr` : '—'}
              </td>
              <td className="num">
                {checkpoint.weather ? `${checkpoint.weather.temperature_f.toFixed(0)}°F` : '—'}
              </td>
              <td>{DRIVER_LABEL[checkpoint.driver] ?? checkpoint.driver}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
