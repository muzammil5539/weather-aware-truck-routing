# Weather-Aware Truck Routing

Compare three road routes between two places and pick the safest, scored on the
weather the truck will actually meet — given when it leaves and what it is
carrying.

![stack](https://img.shields.io/badge/Django-5.2-0B3C49) ![stack](https://img.shields.io/badge/DRF-3.16-0B3C49) ![stack](https://img.shields.io/badge/React-19-125567) ![stack](https://img.shields.io/badge/TypeScript-5-125567) ![tests](https://img.shields.io/badge/tests-148%20passing-1A7F5A)

- **Three route options** from OSRM, topped up with a side-waypoint detour when
  the router offers fewer.
- **A checkpoint every 10 / 25 / 50 miles**, each carrying the forecast for the
  hour the truck is estimated to reach it.
- **Risk per checkpoint** from the wind / rain / snow thresholds, escalated by
  the load rules.
- **A recommendation** balancing weather risk against travel time.
- **A map** of all routes, checkpoints, risk levels, ETAs and summaries.
- **A corridor heatmap** with a 0–48 hour forecast slider.

**No API keys required.** Routing, geocoding and forecasts all come from free,
key-less services, and each has a **backup provider** that takes over when the
primary rate-limits or goes down — so a live demo keeps working:

| Need | Primary | Backup |
|---|---|---|
| Routing | OSRM demo server | FOSSGIS `routed-car` mirror |
| Geocoding | Nominatim | Photon |
| Forecasts | Open-Meteo | MET Norway |

Forecasts are also cached for 30 minutes per coordinate, so replanning the same
trip costs nothing upstream.

---

## Quick start

Two terminals. Requires Python 3.11+ and Node 20+.

**Backend** — http://127.0.0.1:8000

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or: uv venv .venv
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

**Frontend** — http://localhost:5173

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to Django, so no CORS setup is needed locally.
Open http://localhost:5173, enter an origin, a destination, a departure time
and a load weight.

> If `python -m venv` fails with an `ensurepip` error on Debian/Ubuntu, either
> `apt install python3-venv` or use [uv](https://docs.astral.sh/uv/):
> `uv venv .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt`.

---

## Verify

```bash
cd backend && python manage.py test        # 88 tests
```

```bash
cd frontend && npm run lint && npm test && npm run build    # 60 tests
```

All green as of the last commit. `npm run test:coverage` writes an HTML report
to `frontend/coverage/`.

---

## Configuration

Both `.env.example` files list every variable with its default; copy each to
`.env` to change anything. Nothing is required for local development.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev key | Set this in production |
| `DJANGO_DEBUG` | `True` | |
| `DATABASE_URL` | SQLite file | Set for PostgreSQL |
| `CORS_ALLOWED_ORIGINS` | `localhost:5173` | |
| `OSRM_BASE_URLS` | OSRM demo, FOSSGIS mirror | Routing, tried in order |
| `NOMINATIM_BASE_URL` / `PHOTON_BASE_URL` | Nominatim, Photon | Geocoding, primary then backup |
| `OPEN_METEO_BASE_URL` / `MET_NO_BASE_URL` | Open-Meteo, MET Norway | Forecasts, primary then backup |
| `REDIS_URL` | unset (in-process cache) | Share the forecast cache across workers |
| `GEOCODER_USER_AGENT` | project string | Nominatim asks for a contact |
| `VITE_API_BASE_URL` | empty (proxied) | API origin for a production build |

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/trips/` | Plan a trip; returns routes, checkpoints and heatmap |
| `GET` | `/api/trips/{id}/` | Retrieve a saved plan |
| `GET` | `/api/trips/{id}/heatmap/` | The 48-hour corridor grid alone |
| `GET` | `/api/geocode/?q=` | Place suggestions |
| `GET` | `/api/risk-reference/` | Thresholds and load rules |
| `GET` | `/api/health/` | Liveness |

```bash
curl -X POST http://127.0.0.1:8000/api/trips/ \
  -H 'Content-Type: application/json' \
  -d '{"origin":"Denver, CO","destination":"Salt Lake City, UT",
       "departure_at":"2026-10-09T17:00:00Z","load_lb":42000,
       "checkpoint_interval_miles":25}'
```

Full request/response shapes: [docs/DESIGN.md](docs/DESIGN.md#api).

---

## Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

A checkpoint takes the **worst** of the three, then the load rules raise it:

- wind ≥ 55 mph → **No Travel** for any load
- wind 45–54 mph with > 30,000 lb → **No Travel**
- wind 35–44 mph with > 40,000 lb → **Severe**

Routes are ranked by fewest **No Travel** miles, then fewest Severe miles,
fewest High miles, lowest average risk, shortest travel time.

Band edges are lower-inclusive and upper-exclusive — rain of exactly 0.25 in/hr
is High. That and every other judgement call is written down in
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

---

## Project layout

```
backend/
  config/            settings, urls, wsgi
  routing/
    services/        risk · geo · geocode · osrm · weather · planner · http
    models.py        Trip → Route → Checkpoint
    repository.py    writes a plan in one transaction
    serializers.py  views.py  urls.py  exceptions.py
    tests/           88 tests, upstreams faked at the module boundary
frontend/
  src/
    api/             typed client, error translation
    lib/             risk colours and labels, formatting
    components/      form, map, heat layer, slider, route list, table
    pages/           PlanPage, TripView
docs/
  DESIGN.md          architecture, API, components, testing, deployment
  ASSUMPTIONS.md     every judgement call, with its reasoning
```

---

## Deploying

The two halves deploy separately. **Netlify cannot host the Django API** — it
serves static files and serverless functions, not a long-running WSGI process —
so the backend goes somewhere that can run a process, and the frontend is told
where to find it at build time.

### 1. Backend first

`render.yaml` deploys the API to [Render](https://render.com) as a Blueprint.
It sets everything except `CORS_ALLOWED_ORIGINS`, which cannot be known until
the frontend has a URL. Note the API's origin — something like
`https://truck-routing-api.onrender.com` — and check `/api/health/` returns
`{"status": "ok"}`.

> Render's free tier has an ephemeral filesystem, so the default SQLite
> database resets on redeploy. Planned trips are regenerable, so this is fine
> for a demo; attach a Postgres instance and set `DATABASE_URL` to keep them.

### 2. Frontend second

`netlify.toml` is committed at the repo root and already tells Netlify
everything structural: the app is in `frontend/`, not the repo root; the
publish directory is `frontend/dist`; and `/*` rewrites to `/index.html` so
`/trips/{id}` survives a reload.

The one thing it cannot contain is your API's URL. In **Site settings →
Environment variables**, add:

```
VITE_API_BASE_URL = https://truck-routing-api.onrender.com
```

This is read at **build time**, not run time — Vite inlines it into the bundle.
Adding it after a build has no effect until you redeploy, so trigger a fresh
deploy (**Deploys → Trigger deploy → Clear cache and deploy site**).

### 3. Close the loop

Set `CORS_ALLOWED_ORIGINS` on the backend to your Netlify origin
(`https://your-site.netlify.app`, no trailing slash) and redeploy it. Until you
do, the browser will block every API call as a cross-origin request.

---

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — architecture, data model, API, frontend
  structure, testing strategy, deployment.
- [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) — the ambiguities in the brief and
  how each was resolved.
- [Design canvas](https://claude.ai/artifact/BqW7TyZerC9rdN1QRotszd) — the
  design system, components, risk model, states and screens.

---

## Attribution

Routing © [OSRM](https://project-osrm.org/) · Geocoding and map tiles ©
[OpenStreetMap](https://www.openstreetmap.org/copyright) contributors ·
Forecasts © [Open-Meteo](https://open-meteo.com/) (CC BY 4.0).
