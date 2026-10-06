# Website Load Testing Dashboard

A local, authorized **performance and stress testing** tool for websites you own
or have explicit permission to test. It uses *virtual users* to measure how a
site behaves under increasing load, with built‑in safety limits and automatic
stop conditions so it measures capacity rather than trying to take a site down.

> ⚠️ **Authorization warning.** Only test systems you own or are explicitly
> authorized to test. Unauthorized load/stress testing may be illegal and can
> cause outages. This tool requires you to confirm authorization before every
> test and refuses private/internal targets unless you deliberately enable them.

---

## 1. What this application does

- Runs entirely on your machine — no data leaves the host.
- Lets you enter a deployed `http(s)` URL and a set of **authorized GET/HEAD
  paths**, then drives configurable virtual-user load against them.
- Ramps users up gradually (users/second), holds for a bounded duration, and
  **stops automatically** when a safety threshold is crossed.
- Shows a **live dashboard**: active users, RPS, totals, error rate, latency
  percentiles (P50/P95/P99), min/max, and HTTP status distribution, with live
  Plotly charts.
- Stores every run in a local **SQLite** history you can browse, inspect,
  export (CSV/JSON), and delete.

### Architecture at a glance

```
Streamlit UI (app.py)
    │  config (validated by Pydantic)
    ▼
LoadTest controller (core/test_manager.py)
    │  background thread → asyncio event loop
    ├── worker virtual users (httpx.AsyncClient)  → Authorized Target
    └── monitor loop (1 Hz) → metrics + safety thresholds
            │
            ▼
MetricsAggregator (core/metrics.py) → SQLite history (core/database.py)
```

The **default local engine** is an in-process `asyncio` + `httpx` engine. It is
reliable, gives real-time in-process metrics, enforces safety stops within one
second, and shuts workers down gracefully. For **very large** authorized tests a
single laptop cannot generate, an optional **Locust master/worker** path is
provided (see §10).

---

## 2. Installation

Requires **Python 3.11+** (developed/tested on 3.11–3.13).

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
cp .env.example .env               # optional: adjust defaults/caps
```

## 3. Running locally

There are **two UIs**, both driving the same Python load engine — pick one:

### Option A — Next.js UI + FastAPI backend (recommended)

A professional React dashboard (Next.js + Tailwind + Recharts) talking to a
FastAPI wrapper around the engine.

```bash
# Terminal 1 — backend (from the repo root, venv active)
uvicorn api.main:app --port 8000 --reload

# Terminal 2 — frontend
cd web
cp .env.local.example .env.local   # optional
npm install
npm run dev
```

Open **http://localhost:3000**. The frontend proxies `/api/*` to the backend,
so there is nothing else to configure.

Or launch both at once with the helper script:

```bash
./run-dev.sh      # backend on :8000, frontend on :3000
```

### Option B — Streamlit UI (zero Node required)

```bash
streamlit run app.py
```

Opens at **http://localhost:8501**.

### Tests

```bash
pytest            # Python engine + API (51 tests)
cd web && npm run build   # type-check + build the frontend
```

---

## 4. Dashboard usage

1. **Target** — enter the base URL (e.g. `https://example.com`). It is validated
   for scheme/host and rejected if it is localhost/private (unless enabled in
   Settings).
2. **Test configuration** — choose virtual users (presets or custom), ramp-up
   (users/second), duration (presets or custom), and per-request timeout. The
   hard safety caps are shown inline and enforced.
3. **Scenario** — pick `GET` or `HEAD` and enter one authorized path per line.
4. **Safety thresholds** — review/adjust the automatic stop conditions.
5. **Confirm authorization** — tick the confirmation checkbox. The **Start**
   button stays disabled until you do.
6. **Start** — watch the live metrics and charts. Use **STOP TEST** at any time
   for a graceful manual stop. When the test ends you get a summary with a
   PASSED / WARNING / STOPPED / FAILED verdict, which is saved to history.

---

## 5. Understanding virtual users

**Virtual users are simulated clients, not browser windows.** Each virtual user
is a lightweight async task that issues one request at a time against your
authorized paths and immediately issues the next when the previous completes.
100,000 virtual users is **not** 100,000 Chrome windows — it is 100,000
concurrent request loops, which is why very large tests need distributed workers
rather than a single laptop (see §10).

## 6. Understanding RPS

**Requests per second (RPS)** is the throughput: how many requests completed per
second. It is roughly `concurrent_users / average_response_time_seconds`, so RPS
rises as you add users *until* the target saturates — after which latency climbs
while RPS flattens. That inflection point is your practical capacity.

## 7. Understanding P95 / P99

Percentiles describe the *distribution* of response times, which averages hide:

- **P50 (median)** — half of requests were faster than this.
- **P95** — 95% were faster; the slow tail 5% were slower.
- **P99** — the slowest 1%. This is what your least-lucky users feel.

Tail latency (P95/P99) usually degrades long before the average does, so it is
the better capacity signal and is used as an automatic stop condition.

## 8. Understanding error rate

**Error rate** = failed requests ÷ total requests. A request is a failure if the
HTTP status is ≥ 400 or the transport failed (timeout, DNS, connection reset,
SSL error). A rising error rate — especially `429` (rate limited) or `5xx`
(server errors) — means the target is overwhelmed, so these have their own
dedicated stop thresholds.

## 9. Safe load-testing methodology

- **Always have authorization in writing** for the target.
- **Start small** (e.g. 10–50 users) and increase gradually across runs.
- **Ramp up**, don't spike — add users per second so you can see where
  performance degrades.
- **Prefer staging/pre-production** environments.
- **Keep the safety thresholds on.** They stop the test the moment the target
  shows distress.
- **Test off-peak** and tell your ops team beforehand.
- **Read the tail latency**, not just the average.

---

## 10. Distributed testing architecture (optional, disabled by default)

A single Mac can comfortably simulate hundreds to low-thousands of virtual
users; beyond that the bottleneck becomes your own machine (CPU, file
descriptors, local network), not the target. For large authorized tests, scale
out with Locust's master/worker model:

```
            Local Dashboard
                  │
            Load Controller (Locust master)
                  │
   ┌──────────┬───┴───────┬──────────┐
 Worker 1   Worker 2    Worker 3  …  Worker N
   └──────────┴───────────┴──────────┘
                  │
            Authorized Target
```

This repo ships a ready-to-use cluster definition. It only generates load when
*you* start it, and it never provisions cloud servers automatically.

```bash
export LT_TARGET_URL=https://your-authorized-target.example.com
export LT_PATHS=/,/about,/products
docker compose -f docker-compose.distributed.yml up --scale worker=4
# open the Locust UI at http://localhost:8089, set users/spawn-rate/run-time
```

### 100,000 virtual users

100,000 virtual users ≠ 100,000 Chrome windows. For a test that large you would
run many Locust workers (across several machines or containers), each
simulating a slice of the users, coordinated by one master. Keep the local
single-machine mode conservative; use the distributed mode — with explicit
authorization and a defined run time — for scale.

---

## 11. Troubleshooting (macOS)

| Symptom | Fix |
| --- | --- |
| `python3: command not found` or old version | Install Python 3.11+ (`brew install python@3.12`) and re-create the venv. |
| `pip install` fails to build a wheel | Upgrade pip: `pip install --upgrade pip`. |
| Virtual environment not active | Re-run `source .venv/bin/activate`; your prompt should show `(.venv)`. |
| Locust not found | It is optional; `pip install locust` or `pip install -r requirements.txt`. |
| Streamlit not found | `pip install streamlit`; confirm the venv is active. |
| Port 8501 already in use | `streamlit run app.py --server.port 8600`. |
| "Too many open files" at high user counts | Raise the limit: `ulimit -n 10000`, and/or lower virtual users — a single machine has limits (see §10). |
| Can't test `http://localhost:...` | Enable **Allow private targets** in Settings (development only). |

---

## 12. Project structure

```
load-tester/
├── app.py                         # Streamlit entry point (navigation)
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example
├── pytest.ini
├── docker-compose.distributed.yml # optional Locust master/worker cluster
│
├── config/
│   └── settings.py                # env-driven settings + hard safety caps
├── core/
│   ├── test_manager.py            # async load engine (ramp, monitor, stop)
│   ├── validators.py              # URL + private-address validation
│   ├── metrics.py                 # aggregation, percentiles, thresholds
│   └── database.py                # SQLite history + CSV/JSON export
├── api/
│   └── main.py                    # FastAPI backend wrapping the engine (REST)
├── web/                           # Next.js + Tailwind + Recharts frontend
│   ├── app/                       # App Router pages (dashboard/history/settings)
│   ├── components/                # Sidebar, charts, metric tiles, badges
│   └── lib/                       # typed API client + formatting helpers
├── run-dev.sh                     # launch backend + frontend together
├── loadtest/
│   ├── locustfile.py              # optional distributed engine
│   └── scenarios.py               # shared scenario definitions
├── models/
│   └── schemas.py                 # Pydantic config + result models
├── pages/
│   ├── common.py                  # shared state + Plotly charts
│   ├── dashboard.py               # configure / run / monitor / summary
│   ├── test_history.py            # browse / inspect / export / delete
│   └── settings.py                # defaults + safety behaviour
├── data/                          # local SQLite database (gitignored)
└── tests/                         # pytest suite
```

### Component overview

- **models/schemas.py** — the validated contract. `TestConfig` rejects
  unsupported methods, normalizes paths, and refuses ramp-ups longer than the
  test. `SafetyThresholds` holds the auto-stop limits. `TestSummary` is the
  persisted result.
- **config/settings.py** — defaults loaded from `.env`, plus **hard caps**
  (`max_users_hard_cap` default 50,000, `max_duration_hard_cap_s`) that the UI
  cannot exceed, a soft `single_machine_recommended_max` (default 2,000) that
  drives an in-UI warning, and `max_connection_pool` which bounds the HTTP
  connection pool so large VU counts degrade gracefully instead of exhausting
  file descriptors.
- **core/validators.py** — fails closed: only unambiguous public HTTP/HTTPS
  targets pass unless private targets are explicitly enabled; unresolvable hosts
  are treated as unsafe.
- **core/metrics.py** — cheap per-request accumulation with bounded-memory
  reservoir sampling for percentiles, plus `evaluate_thresholds()`.
- **core/test_manager.py** — the engine: a background asyncio loop ramps virtual
  users, a 1 Hz monitor samples metrics and enforces thresholds, and shutdown is
  graceful (stop event → finish in-flight → await with timeout → close client).
- **core/database.py** — local SQLite persistence and export helpers.
- **pages/** — the Streamlit UI (dashboard, history, settings) and charts.
- **loadtest/** — the optional Locust engine for distributed scale.

---

## Security & logging notes

- **No secrets are logged.** Logging records lifecycle events, target,
  configuration, errors, and stop reasons only — never headers, cookies, or
  authorization material.
- **No hardcoded targets or credentials.** The example URL is a placeholder.
- Only **GET/HEAD** are supported; the tool never issues mutating requests.
- The local SQLite database (`data/*.db`) is gitignored.

## Limitations of single-machine load generation

A single Mac is bounded by CPU, available file descriptors/sockets, and its own
network stack. Past roughly a few thousand concurrent virtual users you are
measuring **your laptop**, not the target — which is why the UI shows a warning
above `single_machine_recommended_max` (default 2,000). The hard cap allows up
to 50,000 virtual users for flexibility, and the connection pool is bounded so
the engine degrades gracefully rather than crashing, but for tests at that
scale you should use the **distributed Locust cluster** (§10) across multiple
workers/machines. If you do push high counts locally, raise your file-descriptor
limit first (`ulimit -n 100000`).
