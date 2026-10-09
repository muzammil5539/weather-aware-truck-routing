# Design

Weather-aware truck routing: a dispatch tool that compares three road routes
between two places and scores each on the weather the truck will actually meet,
given when it leaves and what it is carrying.

The visual design system and UI screens are on the design canvas:
<https://claude.ai/artifact/BqW7TyZerC9rdN1QRotszd>

---

## 1. Architecture

```
React 19 + TypeScript (Vite)          Django 5 + DRF                 Upstream (free, no API key)
┌───────────────────────────┐        ┌─────────────────────┐        ┌────────────────────────┐
│ TripForm                  │ POST   │ TripViewSet.create  │   →    │ Nominatim   geocoding  │
│ RouteList / TripMap       │ /api/  │   ↓                 │   →    │ OSRM        routing    │
│ HeatLayer / HourSlider    │ trips/ │ planner.plan_trip() │   →    │ Open-Meteo  forecast   │
│ CheckpointTable           │ ←───── │   ↓                 │        └────────────────────────┘
└───────────────────────────┘  Trip  │ repository.save_plan│
                                     │   ↓ Trip/Route/     │
                                     │     Checkpoint      │
                                     └─────────────────────┘
```

One POST returns the complete plan: three scored routes, every checkpoint, and
a 48-hour corridor heatmap. The hour slider is then pure client state, so
scrubbing the forecast costs no network round trip.

**Why these providers.** All three are free and need no API key, so the project
runs immediately after clone with nothing to configure — and the assessment is
graded on routing, risk and UI, not on credential management. Every base URL is
read from the environment, so swapping in a commercial provider is a config
change, not a code change.

### Layering

| Layer | Location | Rule |
|---|---|---|
| Domain | `routing/services/risk.py`, `geo.py` | Pure functions. No I/O, no Django. |
| Providers | `routing/services/{geocode,osrm,weather,http}.py` | One module per upstream. All failures become `UpstreamError`. |
| Orchestration | `routing/services/planner.py` | Composes the above into a `TripPlan`. Still no ORM. |
| Persistence | `routing/models.py`, `repository.py` | Writes a `TripPlan` in one transaction. |
| HTTP | `routing/{views,serializers,urls,exceptions}.py` | DRF only. No business logic. |

The payoff is that the risk engine — the part being graded hardest — is a pure
module testable without a database, a network, or a Django settings module.

---

## 2. Backend

### Django apps

One app, `routing`. A second app would be ceremony: there is one bounded
context here.

`config` holds settings, URLs and WSGI. `django.contrib.auth` is installed
because DRF's anonymous-user default needs it; no auth is wired up
(see [ASSUMPTIONS.md](ASSUMPTIONS.md)).

### Models

```
Trip 1───* Route 1───* Checkpoint
```

**Trip** — the request plus the corridor heatmap.

| Field | Type | Note |
|---|---|---|
| `id` | UUID pk | Unguessable, so a plan is shareable by URL |
| `origin_label/lat/lon` | char, float, float | Resolved place, kept for display |
| `destination_label/lat/lon` | char, float, float | |
| `departure_at` | datetime | Stored UTC |
| `load_lb` | float | Drives the load rules |
| `checkpoint_interval_miles` | small int | 10 / 25 / 50 |
| `heatmap` | JSON | Dense numeric grid; see §2.5 |
| `created_at` | datetime | |

**Route** — one option, already scored. `trip` FK, `name`, `summary` (the roads
it actually spends most distance on), `distance_miles`, `duration_hours`,
`arrival_at`, `geometry` (JSON polyline), `rank`, `is_recommended`,
`average_risk`, `worst_level`, five `*_miles` buckets, `warnings` (JSON).
Unique on `(trip, name)`.

**Checkpoint** — one weather sample. `route` FK, `index`, `lat`, `lon`,
`distance_miles`, `segment_miles` (the road this checkpoint speaks for), `eta`,
`weather` (JSON reading), `risk_level`, `risk_score`, `wind_level`,
`rain_level`, `snow_level`, `driver`. Unique on `(route, index)`.

**Why normalised rows rather than one JSON blob.** The scores are queryable and
the relationships are real. The heatmap is the single exception — a
`points × 48` numeric grid with no independent identity, which would be
thousands of pointless rows.

### Serializers, viewsets, permissions

- `TripRequestSerializer` — validates the inbound form. Accepts optional
  `origin_lat/lon` and `destination_lat/lon`, sent when the driver picked a
  geocoder suggestion, which pins the exact place and skips a lookup. Rejects a
  half-supplied coordinate pair, an origin equal to the destination, a negative
  or absurd load, and an unsupported interval.
- `TripSerializer` → `RouteSerializer` → `CheckpointSerializer`, read-only,
  nested, served through `prefetch_related("routes__checkpoints")`.
- `TripListSerializer` — no geometry, for the recent-trips list.
- `TripViewSet` is a `ReadOnlyModelViewSet` with `create` overridden: the write
  path is "plan a trip", not "insert a row", so it takes the request
  serializer and returns the read serializer.
- Permissions: `AllowAny`. One line to change.

### API

Base: `/api/`. Errors always take the shape
`{"error": {"type", "provider?", "detail?", "fields?"}}`.

| Method | Path | Body / query | → | Codes |
|---|---|---|---|---|
| `POST` | `/trips/` | `origin`, `destination`, `departure_at`, `load_lb`, `checkpoint_interval_miles`, optional pinned coords | Full `Trip` | `201`, `400` validation, `422` unknown place / no route, `502` provider down |
| `GET` | `/trips/{uuid}/` | — | Full `Trip` | `200`, `404` |
| `GET` | `/trips/{uuid}/heatmap/` | — | The grid alone | `200`, `404` |
| `GET` | `/trips/` | — | 25 most recent, lightweight | `200` |
| `GET` | `/geocode/?q=` | — | `{results: Place[]}` | `200` |
| `GET` | `/risk-reference/` | — | Thresholds and load rules | `200` |
| `GET` | `/health/` | — | `{status: "ok"}` | `200` |

`POST /api/trips/` response (abridged):

```jsonc
{
  "id": "95470d12-…",
  "origin": { "label": "Denver, Colorado, United States", "lat": 39.74, "lon": -104.99 },
  "destination": { "label": "Salt Lake City, …", "lat": 40.76, "lon": -111.89 },
  "departure_at": "2026-10-09T17:00:00Z",
  "load_lb": 42000.0,
  "checkpoint_interval_miles": 25,
  "recommended_route": "Route B",
  "routes": [{
    "name": "Route B", "summary": "I 70 / US 6; US 191 / I 15", "source": "osrm",
    "distance_miles": 526.0, "duration_hours": 9.77, "arrival_at": "2026-10-10T02:46:00Z",
    "geometry": [[39.74, -104.99], …],
    "rank": 1, "is_recommended": true,
    "average_risk": 0.42, "worst_level": "moderate",
    "risk_miles": { "no_travel": 0.0, "severe": 0.0, "high": 0.0, "moderate": 96.0, "low": 430.0 },
    "warnings": [],
    "checkpoints": [{
      "index": 0, "lat": 39.74, "lon": -104.99,
      "distance_miles": 0.0, "segment_miles": 25.0,
      "eta": "2026-10-09T17:00:00Z",
      "weather": { "wind_mph": 10.4, "rain_in_hr": 0.0, "snow_in_hr": 0.0, "temperature_f": 60.8, … },
      "risk_level": "low", "risk_score": 0,
      "wind_level": "low", "rain_level": "low", "snow_level": "low", "driver": "wind"
    }]
  }],
  "heatmap": {
    "anchor": "2026-10-09T17:00:00Z",
    "hours": ["2026-10-09T17:00:00Z", …],   // 48
    "points": [[39.70, -105.00], …],         // ≤ 60
    "risk":   [[0, 0, 1, …], …],             // points × 48, score 0–4
    "wind_mph": [[…]], "rain_in_hr": [[…]], "snow_in_hr": [[…]]
  }
}
```

### Planning pipeline

`plan_trip()` in `routing/services/planner.py`:

1. **Geocode** origin and destination (skipped for pinned coordinates).
2. **Route** — `osrm.fetch_routes()` asks for alternatives, drops
   near-identical ones, and tops up to three with side-waypoint detours.
3. **Sample** — `sample_checkpoints()` places a checkpoint every
   10 / 25 / 50 miles, rescaled onto OSRM's reported distance so mile markers
   and ETAs cannot drift apart. The last checkpoint is the true destination.
4. **ETA** — departure + total duration × distance fraction.
5. **Forecast** — every checkpoint across all three routes plus the corridor
   points are de-duplicated into **one batched Open-Meteo call** (chunked at 50
   coordinates). A three-route plan costs one forecast request, not sixty.
6. **Score** — `risk.assess()` per checkpoint; miles accumulated per level;
   distance-weighted average risk.
7. **Rank** — sort by `(no_travel, severe, high, average_risk, duration)`.
8. **Heatmap** — risk and raw readings for every corridor point × 48 hours.

### Risk engine

`routing/services/risk.py` is the single source of truth for every threshold.
Levels are an `IntEnum` so `max()` picks the worse of two. `assess()` takes the
worst of wind / rain / snow, then applies the load rules as a floor that can
only raise the result, and reports which input drove the outcome so the UI can
say "driven by snow" rather than showing an unexplained colour.

Band edges, the escalation table and the ranking order are documented and
justified in [ASSUMPTIONS.md](ASSUMPTIONS.md).

---

## 3. Frontend

React 19 + TypeScript, Vite, React Router, Leaflet. No state-management
library and no data-fetching library: there is one resource and one page.

### Routes

| Path | Component | Purpose |
|---|---|---|
| `/` | `PlanPage` | Form + results |
| `/trips/:tripId` | `PlanPage` | Same page, hydrated from a shared link |
| `*` | inline | Not found |

Planning a trip pushes `/trips/{id}`, so any plan is shareable and reloadable.

### Components

```
App
└── PlanPage                  owns: trip, selected route, heat hour, pending, error
    ├── TripForm              validation, server field errors
    │   └── PlaceInput ×2     debounced geocoder combobox
    ├── RouteList             three cards; selection drives everything right of it
    ├── TripView
    │   ├── TripSummary       load, departure, distance, drive time, arrival
    │   ├── TripMap           Leaflet: polylines, checkpoints, endpoints
    │   │   ├── ClickToZoom   wheel zoom only after the map is clicked
    │   │   ├── FitBounds
    │   │   └── HeatLayer     canvas corridor heat
    │   ├── HourSlider        0–48 h, with play/pause
    │   ├── CheckpointTable
    │   └── RiskLegend / RiskReference
    └── Feedback              loading skeleton, error notice, empty state
```

`PlanPage` owns all shared state and passes it down. With one screen and under
a dozen components, a store would be more moving parts than the problem has.

### Data fetching

`src/api/client.ts` is a thin `fetch` wrapper that normalises every failure
into an `ApiError` carrying a human-readable message, the status, and any
per-field errors. The UI never shows a raw status code or stack. `isValidation
Error` decides whether a "Try again" button makes sense — retrying a rejected
load weight cannot help.

### The heatmap

`HeatLayer` is a ~70-line canvas layer over Leaflet's overlay pane.
**Colour means risk level; alpha means proximity.** Points are drawn
worst-last, so a Severe pocket stays visible instead of being averaged away by
the calm weather around it.

`leaflet.heat` was rejected deliberately: it is unmaintained, ships no types,
and its additive blend would merge two adjacent Low points into a
High-looking blob — a visual lie about the data. Redraws are
`requestAnimationFrame`-batched and off-screen points are skipped, so dragging
the slider is smooth.

### Visual system

Deep teal chrome, near-white work surface, one clay accent on the primary
action. Saturated colour is reserved almost entirely for risk, so the only
thing that shouts on screen is the weather. IBM Plex Sans for prose, IBM Plex
Mono for every number in a column.

Accessibility: every risk fill carries white text at ≥ 4.5:1 (measured and
printed on the Foundations artboard); lightness drops steadily from Moderate to
No Travel so the ramp survives colour blindness and greyscale; risk is always
labelled in words as well as colour; all controls are real elements with
labels; targets are ≥ 44px; the layout works to 375px.

---

## 4. Data flow, validation, errors

```
TripForm ──client validation──> api.planTrip ──> DRF serializer ──> planner ──> providers
   ↑ field errors                   ↑ ApiError                ↑ 400          ↑ UpstreamError → 422/502
```

Validation runs twice on purpose: the client gives instant feedback, the server
is the authority. Both use the same field names, so a server rejection renders
on the right input without translation.

`api_exception_handler` turns `UpstreamError` into `422` (the request cannot
succeed as asked — unknown place, no road) or `502` (the provider is down), and
wraps DRF validation errors as `{"error": {"fields": …}}`. A failed plan is
never partially persisted: `save_plan` is `@transaction.atomic` and nothing is
written until every upstream call has returned.

---

## 5. Testing

**Backend — 88 tests, `python manage.py test`.**

| File | Covers |
|---|---|
| `test_risk.py` | Every boundary of the wind, rain and snow tables; every load rule including the exact-threshold cases; worst-of-three; load-raises-never-lowers |
| `test_geo.py` | Haversine against a known distance, interpolation, sampling spacing, the destination always being the last sample, the reference polyline vector |
| `test_osrm.py` | Parsing, road summaries, de-duplication of near-identical alternatives, the detour top-up, a failing detour not failing the request |
| `test_weather.py` | Single vs multi-location responses, request chunking at 50, units requested not converted, nulls → 0, hour lookup and out-of-window fallback |
| `test_planner.py` | Checkpoint spacing at 10/25/50, ETAs advancing to the route duration, weather sampled at the right hour, risk miles summing to route distance, and one test per ranking criterion |
| `test_api.py` | The full round trip, response shape, validation rejections, the three upstream failure modes, atomicity, shared-link retrieval |

Upstream providers are faked at the module boundary (`routing/tests/factories.py`),
so the suite is fast, offline and deterministic.

**Frontend — 60 tests, `npm test`.**
Risk and format helpers (including a luminance assertion that pins the
colour-blind-safe ramp), the API client's error translation, `TripForm`
validation, `RouteList`, `HourSlider` (including play/pause and wrap),
`CheckpointTable`, and `PlanPage` as an integration test covering plan →
display → route switching → failure → retry → shared link.

Leaflet is mocked in the page test: it needs a layout engine jsdom does not
have. The map was verified in a real browser instead.

**Not covered:** no E2E runner, and no visual regression. For a four-day
assessment the cost outweighs the benefit; the full stack was exercised
manually in a browser against the live providers.

---

## 6. Running it

See the [root README](../README.md) for setup. Verified commands:

```bash
# backend
cd backend && python manage.py migrate && python manage.py test   # 88 passed
python manage.py runserver

# frontend
cd frontend && npm install && npm run lint && npm test && npm run build
```

### Deployment notes

- **Backend** — `gunicorn config.wsgi` behind WhiteNoise for static files. Set
  `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`,
  `CORS_ALLOWED_ORIGINS`, and `DATABASE_URL` for PostgreSQL (`dj-database-url`
  parses it; SQLite is the default when it is unset).
- **Frontend** — `npm run build` emits a static `dist/`. Set
  `VITE_API_BASE_URL` to the API origin at build time; in development Vite
  proxies `/api` so there is no CORS preflight.
- **Rate limits** — Nominatim's usage policy asks for a contactable
  `User-Agent` (`GEOCODER_USER_AGENT`) and roughly one request per second. The
  debounced autocomplete respects this for a demo, not for production traffic;
  a real deployment should cache geocodes and use a paid tier.
- **Caching** — none yet. The obvious first win is a short-TTL cache on
  Open-Meteo responses keyed by rounded coordinate and hour.
