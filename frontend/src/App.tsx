import { Link, Route, Routes } from 'react-router-dom'
import { PlanPage } from './pages/PlanPage'

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <span className="app__mark" aria-hidden="true">
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#fff"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M1 7h12v9H1z" />
            <path d="M13 10h4.5L21 13.5V16h-8z" />
            <circle cx="6" cy="18.5" r="1.8" />
            <circle cx="17" cy="18.5" r="1.8" />
          </svg>
        </span>
        <h1>
          <Link to="/" style={{ color: 'inherit', textDecoration: 'none' }}>
            Weather-Aware Truck Routing
          </Link>
        </h1>
        <span className="app__tagline">Routes scored on wind, rain, snow and load</span>
      </header>

      <Routes>
        <Route path="/" element={<PlanPage />} />
        <Route path="/trips/:tripId" element={<PlanPage />} />
        <Route
          path="*"
          element={
            <main className="app__content">
              <div className="notice notice--empty">
                <p style={{ margin: 0, fontWeight: 600 }}>Page not found.</p>
                <p style={{ margin: '6px 0 0' }}>
                  <Link to="/">Plan a trip instead</Link>
                </p>
              </div>
            </main>
          }
        />
      </Routes>
    </div>
  )
}
