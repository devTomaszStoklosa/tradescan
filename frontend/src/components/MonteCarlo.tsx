/** Monte Carlo of a run's trades: for one backtest run, and for pinned runs side by side. */
import type { EngineRunOut, MonteCarloMethodOut, MonteCarloOut } from "../api/client";
import { MIN_TRADES } from "../lib/compare";
import { DASH, fmtNumber, fmtPct } from "../lib/format";
import { actualRuin, LUCK_LABELS, percentileFor, type Luck, type MonteCarloValue } from "../lib/monteCarlo";
import { asSetup, type PinnedRun, type RunKind } from "../lib/runs";
import { RunLabel } from "./RunCard";
import { Notice } from "./ui";

type Value = number | null | undefined;

const fmtStreak = (value: Value) =>
  value === null || value === undefined ? DASH : fmtNumber(value, Number.isInteger(value) ? 0 : 1);

const FORMATS: Record<MonteCarloValue, (value: Value) => string> = {
  final_return_pct: (value) => fmtPct(value, 1, true),
  max_drawdown_pct: (value) => fmtPct(value, 1),
  longest_losing_streak: fmtStreak,
};

const VALUES: { key: MonteCarloValue; label: string }[] = [
  { key: "final_return_pct", label: "Final return" },
  { key: "max_drawdown_pct", label: "Max drawdown" },
  { key: "longest_losing_streak", label: "Longest losing streak (trades)" },
];

const LUCK: Luck[] = ["unlucky", "median", "lucky"];

export const LUCK_NOTE =
  "Unlucky and lucky are the 5th and 95th percentiles: 1 simulation in 20 did worse than unlucky, 1 in 20 better than lucky.";

/** How the simulations trade, in one sentence. */
export const describeModel = (monteCarlo: MonteCarloOut): string =>
  `${monteCarlo.trades} closed trades resampled ${monteCarlo.simulations.toLocaleString("en-US")} times per method (seed ${monteCarlo.seed}); ` +
  `each trade moves equity by ${fmtNumber(monteCarlo.risk_pct, 2)}% × its R, with no cap on position size.`;

const ruinLabel = (monteCarlo: MonteCarloOut) =>
  `Chance of ruin (drawdown ≥ ${fmtNumber(monteCarlo.ruin_drawdown_pct, 0)}%)`;

const numeric = "num px-3 py-1.5 whitespace-nowrap";
const cell = `${numeric} text-right`;

/** The run's own order of trades next to every method's unlucky, median and lucky values, for one engine's run. */
export function MonteCarloPanel({ run }: { run: EngineRunOut }) {
  const monteCarlo = run.monte_carlo;
  if (!monteCarlo) {
    return <Notice>Too few closed trades for a Monte Carlo of this run: it needs at least two.</Notice>;
  }
  const methods = monteCarlo.methods;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">Monte Carlo of the trades ({run.engine})</h2>
      <p className="text-xs text-muted">
        {describeModel(monteCarlo)} {methods.map((method) => `${method.label}: ${method.description}.`).join(" ")}
      </p>
      <div className="relative overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full text-sm">
          <caption className="sr-only">Monte Carlo of the run's trades</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" rowSpan={2} className="sticky left-0 bg-panel px-3 py-2 text-left font-medium">
                Value
              </th>
              <th scope="col" rowSpan={2} className="px-3 py-2 text-right font-medium">
                This run's order
              </th>
              {methods.map((method) => (
                <th
                  key={method.name}
                  scope="colgroup"
                  colSpan={LUCK.length}
                  className="border-l border-line px-3 pt-2 text-center font-medium"
                >
                  {method.label}
                </th>
              ))}
            </tr>
            <tr className="border-b border-line text-xs text-muted">
              {methods.flatMap((method) =>
                LUCK.map((luck, index) => (
                  <th
                    key={`${method.name}-${luck}`}
                    scope="col"
                    className={`px-3 pb-2 text-right font-normal ${index === 0 ? "border-l border-line" : ""}`}
                  >
                    {LUCK_LABELS[luck]}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {VALUES.map((value) => (
              <tr key={value.key} className="border-b border-line">
                <th
                  scope="row"
                  className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal whitespace-nowrap text-muted"
                >
                  {value.label}
                </th>
                <td className={cell}>{FORMATS[value.key](monteCarlo.actual[value.key])}</td>
                {methods.flatMap((method) =>
                  LUCK.map((luck, index) => (
                    <td
                      key={`${method.name}-${luck}`}
                      className={`${cell} ${index === 0 ? "border-l border-line" : ""}`}
                    >
                      {FORMATS[value.key](percentileFor(method[value.key], value.key, luck))}
                    </td>
                  )),
                )}
              </tr>
            ))}
            <tr>
              <th
                scope="row"
                className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal whitespace-nowrap text-muted"
              >
                {ruinLabel(monteCarlo)}
              </th>
              <td className={cell}>{actualRuin(monteCarlo) ? "reached" : "not reached"}</td>
              {methods.map((method) => (
                <td
                  key={method.name}
                  colSpan={LUCK.length}
                  className={`${numeric} border-l border-line text-center ${method.ruin_pct > 0 ? "text-down" : ""}`}
                >
                  {fmtPct(method.ruin_pct, 1)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        {LUCK_NOTE} The model leaves out the position cap and any trade still open, so its numbers differ from the
        backtest's.
      </p>
      {monteCarlo.trades < MIN_TRADES && (
        <p className="text-xs text-warn">Only {monteCarlo.trades} trades: too few for the spread to mean much.</p>
      )}
    </section>
  );
}

const COMPARED: { key: MonteCarloValue; label: string; luck: Luck[] }[] = [
  { key: "final_return_pct", label: "Final return", luck: ["unlucky", "median"] },
  { key: "max_drawdown_pct", label: "Max drawdown", luck: ["unlucky", "median"] },
  { key: "longest_losing_streak", label: "Losing streak", luck: ["unlucky", "median"] },
];

function MethodValues({ monteCarlo, method }: { monteCarlo: MonteCarloOut; method: MonteCarloMethodOut }) {
  const few = monteCarlo.trades < MIN_TRADES;
  return (
    <>
      <td className={`${cell} ${few ? "text-warn" : ""}`}>
        {monteCarlo.trades}
        {few && (
          <>
            <span aria-hidden>*</span>
            <span className="sr-only"> (fewer than {MIN_TRADES} trades)</span>
          </>
        )}
      </td>
      {COMPARED.flatMap((value) =>
        value.luck.map((luck, index) => (
          <td key={`${value.key}-${luck}`} className={`${cell} ${index === 0 ? "border-l border-line" : ""}`}>
            {FORMATS[value.key](percentileFor(method[value.key], value.key, luck))}
          </td>
        )),
      )}
      <td className={`${cell} border-l border-line ${method.ruin_pct > 0 ? "text-down" : ""}`}>
        {fmtPct(method.ruin_pct, 1)}{" "}
        <span className="text-muted">at {fmtNumber(monteCarlo.ruin_drawdown_pct, 0)}%</span>
      </td>
    </>
  );
}

/** Why a pinned run has no Monte Carlo. */
const NO_MONTE_CARLO: Record<RunKind, string> = {
  backtest: "No Monte Carlo: pinned before Monte Carlo results or with fewer than two closed trades.",
  portfolio: "No Monte Carlo: the portfolio backtest does not simulate its trades.",
  rotation: "No Monte Carlo: the rotation does not simulate its holdings.",
};

/** One row per pinned run: one method's unlucky and median values and the chance of ruin. */
export function MonteCarloTable({ runs, method }: { runs: PinnedRun[]; method: string }) {
  const columns = 2 + COMPARED.reduce((total, value) => total + value.luck.length, 0);
  return (
    <div className="space-y-1">
      <div className="relative overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full text-sm">
          <caption className="sr-only">Monte Carlo of the pinned runs' trades</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" rowSpan={2} className="sticky left-0 bg-panel px-3 py-2 text-left font-medium">
                Run
              </th>
              <th scope="col" rowSpan={2} className="px-3 py-2 text-right font-medium">
                Trades
              </th>
              {COMPARED.map((value) => (
                <th
                  key={value.key}
                  scope="colgroup"
                  colSpan={value.luck.length}
                  className="border-l border-line px-3 pt-2 text-center font-medium"
                >
                  {value.label}
                </th>
              ))}
              <th scope="col" rowSpan={2} className="border-l border-line px-3 py-2 text-right font-medium">
                Chance of ruin
              </th>
            </tr>
            <tr className="border-b border-line text-xs text-muted">
              {COMPARED.flatMap((value) =>
                value.luck.map((luck, index) => (
                  <th
                    key={`${value.key}-${luck}`}
                    scope="col"
                    className={`px-3 pb-2 text-right font-normal ${index === 0 ? "border-l border-line" : ""}`}
                  >
                    {LUCK_LABELS[luck]}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const monteCarlo = asSetup(run)?.monteCarlo;
              const result = monteCarlo?.methods.find((item) => item.name === method);
              return (
                <tr key={run.id} className="border-b border-line last:border-0">
                  <th scope="row" className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal">
                    <RunLabel run={run} />
                  </th>
                  {monteCarlo && result ? (
                    <MethodValues monteCarlo={monteCarlo} method={result} />
                  ) : (
                    <td colSpan={columns} className="px-3 py-1.5 text-muted">
                      {monteCarlo ? "No simulations with this method." : NO_MONTE_CARLO[run.kind]}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        * fewer than {MIN_TRADES} trades. {LUCK_NOTE} Each trade moves equity by the run's risk per trade × its R.
      </p>
    </div>
  );
}
