# tradescan documentation

tradescan is a trading-signal scanner and strategy backtester for daily bars. A Python package
(pandas, FastAPI, SQLite, optional backtrader) provides a command line and an HTTP API; a React app on top of the
API is the web UI. It is a research tool, not investment advice.

## Where to start

| You want to | Read |
| --- | --- |
| Install it, see every screen and command, learn the trading rules | [../README.md](../README.md) |
| Use it as a trader, in Polish, step by step | [INSTRUKCJA.md](INSTRUKCJA.md) |
| Understand how the code is organised and why | [architecture.md](architecture.md) |
| Find the file that does something | [modules.md](modules.md) |
| Call the HTTP API | [api.md](api.md) |
| Know what is stored where: data, cache, settings, database | [data-and-storage.md](data-and-storage.md) |
| Work on the web UI | [frontend.md](frontend.md) |
| Set up a dev environment, run tests, add a signal, rule, engine or endpoint | [development.md](development.md) |
| See what is done and planned | [../ROADMAP.md](../ROADMAP.md) |

## Reading order for a new developer

1. [../README.md](../README.md), the sections "How it works" and "Parameters": the domain rules.
2. [architecture.md](architecture.md): layers, composition, the declared-parameter system, the two engines.
3. [development.md](development.md): get a working environment and the quality checks green.
4. [modules.md](modules.md) as a map while reading code; [api.md](api.md), [data-and-storage.md](data-and-storage.md)
   and [frontend.md](frontend.md) when you touch those areas.

## Documents at a glance

- **[architecture.md](architecture.md)**: layer diagram, dependency injection (`build_use_cases`), the `param(...)`
  system, settings flow, signals and scanner, backtest design (rules vs engines, in-sample/out-of-sample, sweep,
  walk-forward, Monte Carlo, portfolio, rotation), one request end to end, persistence, security model.
- **[modules.md](modules.md)**: one line per module under `src/tradescan`, plus config, scripts and tests.
- **[api.md](api.md)**: conventions, error codes, every endpoint, security, examples, regenerating frontend types.
- **[data-and-storage.md](data-and-storage.md)**: data provider contract, Parquet cache, watchlist format,
  `settings.toml` reference, SQLite schema and migrations, exports.
- **[frontend.md](frontend.md)**: stack, layout, routes, generated types, URL-as-state, generated forms, pinned
  runs, testing, adding a page.
- **[development.md](development.md)**: setup, commands, tests, extension checklist, conventions, workflow,
  troubleshooting.

## Keeping these documents current

User-visible behaviour and trading rules are documented in the README and the Polish manual; this folder
documents structure and workflows. When a pull request changes one of the following, update the matching file in
the same pull request:

| Change | Update |
| --- | --- |
| New or moved module, new layer dependency | [modules.md](modules.md), [architecture.md](architecture.md) |
| New endpoint, field or error mapping | [api.md](api.md) |
| New settings section or key, schema migration, cache layout | [data-and-storage.md](data-and-storage.md) |
| New page, route or state provider | [frontend.md](frontend.md) |
| New tool, command or convention | [development.md](development.md) |
