# Assumptions

Decisions made where the assessment brief was silent or ambiguous. Each notes
what the brief said, what was assumed, and why.

## Risk table band edges

**Brief:** `Rain  <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00`

The printed bands share their edges: 0.25 in/hr appears in both the Moderate
and the High column.

**Assumed:** bands are **lower-inclusive, upper-exclusive**, so 0.25 in/hr is
High. The only strict inequality the brief actually writes is at the No Travel
edge (`>1.00`, `>3.0`, `≥55`), so the Severe band is the one that also contains
its upper edge — rain of exactly 1.00 in/hr is Severe, and No Travel begins
above it. Wind is the stated exception: `≥55` means 55.0 mph is itself No
Travel.

Encoded once in [`backend/routing/services/risk.py`](../backend/routing/services/risk.py)
and pinned by a test for every boundary value.

## Combining the three conditions

**Brief:** gives a table per condition but does not say how wind, rain and snow
combine at one checkpoint.

**Assumed:** the checkpoint takes the **worst** of the three. A driver is not
safer in severe wind because it happens not to be snowing. The load rules are
then applied as a floor that can only raise the result, never lower it.

## "No Travel" in the recommendation order

**Brief:** prefer (1) fewest Severe miles, (2) fewest High miles, (3) lowest
average risk, (4) shortest travel time. No Travel is not mentioned.

**Assumed:** **fewest No Travel miles ranks above all four.** A stretch the
truck must not drive outranks every trade-off below it. The brief's four
criteria follow in exactly the stated order.

Routes with No Travel miles are still shown, ranked last, with an explicit
warning — the brief asks to show all routes, and hiding one would leave a
dispatcher unable to see why it was rejected.

## Average risk

**Brief:** "lowest average risk", without defining the average.

**Assumed:** a **distance-weighted** mean of the checkpoint scores
(Low 0 … No Travel 4), where each checkpoint speaks for the road from itself to
the next checkpoint. An unweighted mean would let a dense cluster of
checkpoints near a city outvote a long exposed stretch of highway.

## Three route options

**Brief:** "Generate 3 route options using a routing API."

OSRM's `alternatives` parameter is best-effort and commonly returns only one or
two routes for a given pair (verified: Denver → Salt Lake City yields two, at
any `alternatives` value).

**Assumed:** top up to three by routing through a waypoint offset
perpendicular to the corridor, the way a dispatcher forces a different highway.
These are labelled `source: "detour"` and shown as "alternate corridor" in the
UI, so a real alternative is never passed off as something it is not. If even
the detours fail, fewer routes are returned rather than duplicates.

## Checkpoint ETAs

**Brief:** "using the truck's estimated arrival time at each checkpoint".

**Assumed:** the ETA at a checkpoint is the departure time plus the route's
total duration scaled by the fraction of the route's distance covered. OSRM
returns per-step durations that would be more precise, but a distance-
proportional split is accurate to a few minutes over a long haul — far inside
the one-hour resolution of the forecast it feeds. Marked in the code as a known
simplification with its upgrade path.

Checkpoint mile markers are rescaled onto OSRM's reported route distance, since
the decoded polyline's own length differs from it slightly through vertex
simplification. Without that, mile markers and ETAs would drift apart.

## Checkpoint spacing

**Brief:** "Sample weather every 10 / 25 / 50 miles".

**Assumed:** the driver chooses which of the three. 25 miles is the default.
The final checkpoint is always the true destination rather than a point at a
round multiple of the interval, so the last row of the table is where the truck
actually arrives.

## Authentication

**Brief:** no mention of users, accounts, roles or sign-in. The deliverable is a
tool a driver opens and uses.

**Assumed:** **no authentication.** Trips are stored anonymously and addressed
by an unguessable UUID, which makes a planned trip shareable by URL — useful
for handing a plan to a dispatcher. Adding accounts would have been scope the
brief did not ask for, against its own instruction to prioritise correctness and
clarity over extra features.

The API is therefore open. For a real deployment this is the first thing to
change; `REST_FRAMEWORK` in `backend/config/settings.py` is the single place to
do it.

## Weather provider and units

**Assumed:** [Open-Meteo](https://open-meteo.com) for forecasts, OSRM for
routing, Nominatim for geocoding — all free and **requiring no API key**, so the
project runs immediately after clone with nothing to configure. Every base URL
is environment-driven, so swapping in a commercial provider is a config change.

Units are requested from Open-Meteo directly in the units the risk table uses
(mph, inches per hour), so no conversion happens anywhere in the codebase and
there is no conversion bug to have.

Open-Meteo serves about 16 days of forecast. A departure beyond that falls back
to the nearest hour held, rather than dropping the checkpoint.

## Heatmap resolution

**Brief:** "a weather heatmap along the trip corridor with a 0–48 hour forecast
slider".

**Assumed:** the corridor is sampled at up to 60 points across all three
routes, and all 48 hours are computed server-side and sent with the trip. The
slider is then pure client-side state, so scrubbing is instant with no network
round trip. Hour 0 is the departure hour.

Colour means risk level and alpha means proximity. An additive intensity
heatmap — the usual `leaflet.heat` behaviour — would blend two adjacent Low
points into a High-looking blob, which would misrepresent the data.

## Load weight ceiling

**Assumed:** 200,000 lb as an upper bound on the input, well above any legal US
gross weight, purely to reject typos. The brief sets no limit.
