import { RISK_COLOR, RISK_LABEL, RISK_ORDER, RISK_THRESHOLDS } from '../lib/risk'

export function RiskLegend() {
  return (
    <div className="legend">
      {RISK_ORDER.map((level) => (
        <span key={level}>
          <span
            className="legend__swatch"
            style={{ background: RISK_COLOR[level] }}
            aria-hidden="true"
          />
          {RISK_LABEL[level]}
        </span>
      ))}
    </div>
  )
}

const ROWS = [
  { label: 'Wind (mph)', unit: '', values: RISK_THRESHOLDS.wind_mph, last: '≥ 55' },
  { label: 'Rain (in/hr)', unit: '', values: RISK_THRESHOLDS.rain_in_hr, last: '> 1.00' },
  { label: 'Snow (in/hr)', unit: '', values: RISK_THRESHOLDS.snow_in_hr, last: '> 3.0' },
]

/** The thresholds table, so a driver can check the app's reasoning. */
export function RiskReference() {
  return (
    <details className="panel">
      <summary style={{ padding: '12px 14px', cursor: 'pointer', fontWeight: 600 }}>
        Risk thresholds &amp; load rules
      </summary>
      <div className="panel__body" style={{ paddingTop: 0 }}>
        <div className="tablewrap">
          <table className="checkpoints" style={{ minWidth: 460 }}>
            <thead>
              <tr>
                <th scope="col">Condition</th>
                {RISK_ORDER.map((level) => (
                  <th key={level} scope="col">
                    {RISK_LABEL[level]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label}>
                  <th scope="row" style={{ textAlign: 'left' }}>
                    {row.label}
                  </th>
                  <td className="num">&lt; {row.values[0]}</td>
                  <td className="num">
                    {row.values[0]}–{row.values[1]}
                  </td>
                  <td className="num">
                    {row.values[1]}–{row.values[2]}
                  </td>
                  <td className="num">
                    {row.values[2]}–{row.values[3]}
                  </td>
                  <td className="num">{row.last}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul
          style={{
            margin: '12px 0 0',
            paddingLeft: 18,
            fontSize: '0.83rem',
            color: 'var(--ink-muted)',
          }}
        >
          <li>Wind ≥ 55 mph is No Travel for any load.</li>
          <li>Wind 45–54 mph with more than 30,000 lb is No Travel.</li>
          <li>Wind 35–44 mph with more than 40,000 lb is Severe.</li>
        </ul>
      </div>
    </details>
  )
}
