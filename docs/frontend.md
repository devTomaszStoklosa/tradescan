# Frontend

A single-page app in `frontend/`: React 19, TypeScript (strict, `tsc --noEmit`), Vite, Tailwind CSS 4, React
Router 7, TanStack Query 5 and `lightweight-charts` for candles and equity curves. Tests: Vitest, jsdom and
Testing Library. Lint and format: ESLint and Prettier.

The UI contains **no trading logic**. It builds requests, calls the API, and renders results. Every number it
can change comes from the server's parameter declarations (see
[architecture.md](architecture.md#the-declared-parameter-system)).

## Run, build, test

```bash
npm --prefix frontend install
npm --prefix frontend run build        # tsc --noEmit && vite build, writes frontend/dist
tradescan serve                        # serves the API and frontend/dist on :8000

# development: API and Vite side by side; Vite proxies /api to 127.0.0.1:8000
tradescan serve
npm --prefix frontend run dev

npm --prefix frontend test             # vitest run
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run format:check
```

`tradescan serve --static PATH` serves another build directory; without `frontend/dist` the server runs the API
only and prints a warning.

## Layout of `frontend/src`

| Path | Contents |
| --- | --- |
| `main.tsx`, `App.tsx` | Entry; providers and the router. Pages are lazy-loaded so the chart library downloads with the first page that needs it. |
| `pages/` | One component per screen, each with a `*.test.tsx` next to it. |
| `components/` | Shared UI: `ui.tsx` primitives, form field groups, result tables, charts (`components/charts/`). |
| `lib/` | Pure logic: form state ↔ URL, request builders, comparison, formatting, runs. Mostly framework-free and unit-tested. |
| `api/` | `client.ts` (typed fetch wrapper), `hooks.ts` (TanStack Query hooks), `schema.ts` (**generated**). |
| `state/` | React contexts: `account`, `pinnedRuns`, `theme`. |
| `test/` | Test setup, fetch mock, fixtures, an in-memory run store. |
| `index.css` | Tailwind import and the semantic colour tokens for both themes. |

### Screens (routes)

| Route | Page | Backend endpoint |
| --- | --- | --- |
| `/` | `ScanPage` | `/api/scan` (its response includes the market regime), `/api/chart`, `/api/edge` (ticker panel) |
| `/backtest` | `BacktestPage` | `/api/backtest` |
| `/sweep` | `SweepPage` | `/api/sweep` |
| `/walk-forward` | `WalkForwardPage` | `/api/walk-forward` |
| `/watchlist` | `WatchlistPage` | `/api/watchlist-backtest` |
| `/portfolio` | `PortfolioPage` | `/api/portfolio-backtest` |
| `/rotation` | `RotationPage` | `/api/rotation-backtest` |
| `/rotation-sweep` | `RotationSweepPage` | `/api/rotation-sweep` |
| `/edge` | `EdgePage` | `/api/edge` |
| `/compare` | `ComparePage` | `/api/runs` (pinned runs, client-side comparison) |
| `/journal` | `JournalPage` | `/api/journal` |
| `/signals` | `SignalsPage` | `/api/signals` |

The navigation list is in `components/Layout.tsx`; the routes are in `App.tsx`.

## Key design points

### Types come from the API

`api/schema.ts` is generated from the OpenAPI schema (`python scripts/export_openapi.py frontend/openapi.json`,
then `npm --prefix frontend run gen:api`) and committed. `api/client.ts` re-exports the models under short
names and wraps `fetch` in a typed `api` object (errors become `ApiError` with the server's `detail`). Renaming
a field in `api/schemas/*.py` therefore breaks the TypeScript build until the UI is updated. Regenerate the
types after every API model change.

### Data fetching

`api/hooks.ts` wraps each endpoint in a TanStack Query hook. Analysis hooks share `useRun(key, fetch, body)`:
the body is part of the query key and a `null` body means "waiting" (`skipToken`), so a form that is not
submitted or not valid fires nothing. Results are fresh for 5 minutes and are not retried; config, signals and
watchlists are fetched once (`staleTime: Infinity`). Window-focus refetch is off.

### Forms live in the URL

Each page's form state is serialized to the URL (`lib/params.ts` and the per-page `lib/*.ts` files), so a scan
or backtest can be bookmarked, shared or opened in two tabs. Only values that differ from the defaults are kept
(`lib/overrides.ts`), which keeps links short:

- settings overrides: `set.<section>.<name>=<value>`
- signal parameters: `sig.<signal>.<name>=<value>`
- rules: `entry=<rule>`, `exit=<rule>,<rule>` (`none` for no exits), `filter=<rule>,...`, parameters as
  `en.<rule>.<name>` / `ex.<rule>.<name>` / `fi.<rule>.<name>`; benchmark `b=<ticker>`
- universe: `w=<watchlist>` or `t=<tickers>`; engines `eng=...`
- sweep axes: `ax1=signal.oversold&ax1v=5:20:1`; walk-forward adds `scheme=anchored`

Pages link to each other through these URLs (a sweep cell opens as a Backtest, a watchlist ticker opens its own
backtest, a compared run opens in its page).

### Forms are generated from declarations

`GET /api/config` and `/api/signals` provide `ParamSpecOut` (kind, default, min, max, step, label, unit, help)
for every parameter and rule. `ParamFields`, `AdvancedSettings`, `TradeRuleFields` and `lib/rules.ts` build
inputs and validation from them, highlight changed values and check ranges. **A parameter added on the server
shows up in the UI, the URL, pinned runs, Compare and sweeps with no frontend change.** Labels and units in
Compare also come from the specs.

### Pinned runs and Compare

A pin (`lib/runs.ts`) is a frozen snapshot of one engine's result: a backtest, a portfolio or a rotation run. It is
never re-run, so new bars do not change it; "Open in Backtest/Portfolio/Rotation" runs the same setup again.
At most 8 runs (`MAX_RUNS`, also the size of the run colour palette; the server enforces the same limit).
`state/pinnedRuns.tsx` loads and changes them through a `RunStore` (`lib/runStore.ts`); `serverRunStore` talks
to `/api/runs`, tests inject an in-memory store. `lib/runsFile.ts` defines the on-disk format (`{version,
runs}`, each equity curve as two arrays with values rounded to cents, about half the size of one object per
point), used by both the server storage and Export/Import JSON; the snapshot carries its `format` so older
snapshots are upgraded when read. `lib/pinnedSettings.ts` reproduces the settings a pin used. Runs pinned by
versions that kept them in the browser (`localStorage` key `tradescan.runs`) are migrated to the server on first
open.

### Browser-only state

- `state/account.tsx`: account size, risk per trade, max position and lot size, stored in `localStorage`
  (`tradescan.account`); `null` means "use the server default". They become `account` settings overrides.
- `state/theme.tsx` and `components/ThemeToggle.tsx`: light/dark theme. Colours are semantic CSS tokens in
  `index.css`; canvas charts read them through `lib/cssVar.ts` so they follow the theme.
- `lib/storage.ts`: `readStorage` / `writeStorage` / `useStoredState` swallow `localStorage` errors (private
  mode, blocked data) and fall back silently.

### Components worth knowing

`components/ui.tsx` holds the shared primitives (`PageHeader`, `Panel`, `Button`, `Field`, `NumberInput`,
`Segmented`, `ToggleChip`, `StatTile`, `Loading`, `ErrorBox`, `EmptyState`, `Notice`). `EnginePicker` is shared
by Backtest, Portfolio and Rotation. `RunCard` shows what is specific to each kind of run (a new kind adds its
entry there). Sweep, walk-forward and rotation-sweep results use `SweepHeatmap` and `SweepResults`.
`components/charts/` wraps `lightweight-charts` (`PriceChart`, `EquityChart`).

## Testing

`vitest` with jsdom (`vite.config.ts`, setup in `test/setup.ts`). Tests mock the API with `test/fetch.ts` and
`test/fixtures.ts` and never need a server. `lib/` modules have unit tests (`*.test.ts`); pages and key
components have `*.test.tsx`. The setup raises the async-utility timeout to 3 s because a page's first render
in a file can be slow while every worker is busy, and stubs `scrollIntoView`, which jsdom lacks.

## Adding a page

1. Add `lib/<feature>.ts`: form type, defaults, URL read/write, and the request builder (reuse
   `lib/overrides.ts` and `lib/rules.ts`).
2. Add the endpoint to `api/client.ts` (and a `use<Feature>` hook in `api/hooks.ts`) after regenerating
   `schema.ts`.
3. Add `pages/<Feature>Page.tsx` with a test, a lazy route in `App.tsx` and a link in `Layout.tsx`.
4. If its result should be comparable, add a run kind in `lib/runs.ts` and `components/RunCard.tsx`.
