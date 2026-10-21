import { Link } from "react-router";

import type { Direction } from "../api/client";
import { MIN_TRADES } from "../lib/compare";
import { fmtPct } from "../lib/format";
import { writeBacktestForm } from "../lib/params";
import { reopenedSettings } from "../lib/pinnedSettings";
import { writePortfolioForm } from "../lib/portfolio";
import { writeRotationForm } from "../lib/rotation";
import { runColorVar, runStrategy, runSubject, type PinnedRun, type RunKind } from "../lib/runs";
import { useResettableState } from "../lib/useResettableState";
import { Button, DirectionBadge, Input } from "./ui";

/** What a card shows only for one kind of run; a new kind of run adds its entry here. */
interface CardSpec<R extends PinnedRun> {
  /** What the run covered, shown before its engine; null when the subject says it all. */
  scope: (run: R) => string | null;
  /** The side the run traded; null when it only buys. */
  direction: (run: R) => Direction | null;
  /** How the run picked its trades. */
  description: (run: R) => string;
  /** The page that runs the same setup again. */
  open: (run: R) => { label: string; to: string };
}

const CARDS: { [K in RunKind]: CardSpec<Extract<PinnedRun, { kind: K }>> } = {
  backtest: {
    scope: () => null,
    direction: (run) => run.direction,
    description: (run) => run.description,
    open: (run) => ({
      label: "Open in Backtest",
      to: `/backtest?${writeBacktestForm({ ...run.form, settings: reopenedSettings(run) }).toString()}`,
    }),
  },
  portfolio: {
    scope: (run) => `portfolio of ${run.tickers.length} tickers`,
    direction: (run) => run.direction,
    description: (run) => run.description,
    open: (run) => ({
      label: "Open in Portfolio",
      to: `/portfolio?${writePortfolioForm({ ...run.form, settings: reopenedSettings(run) }).toString()}`,
    }),
  },
  rotation: {
    scope: (run) => `rotation of ${run.tickers.length} tickers, top ${run.rotation.holdings} ${run.rotation.rebalance}`,
    direction: () => null,
    description: (run) => `Ranking: ${run.ranking.description} · weights: ${run.weighting.description}`,
    open: (run) => ({
      label: "Open in Rotation",
      to: `/rotation?${writeRotationForm({ ...run.form, settings: reopenedSettings(run) }).toString()}`,
    }),
  },
};

const cardOf = <R extends PinnedRun>(run: R) => CARDS[run.kind] as unknown as CardSpec<R>;

/** The page and link that run the same setup again. */
export const openRun = (run: PinnedRun) => cardOf(run).open(run);

/** A run's colour, number and name, as used in table headers. */
export function RunLabel({ run }: { run: PinnedRun }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span
        aria-hidden
        className="inline-block size-2.5 shrink-0 rounded-full"
        style={{ background: `var(${runColorVar(run)})` }}
      />
      <span className="num text-muted">#{run.slot}</span>
      <span className="text-fg">{run.name}</span>
    </span>
  );
}

export function RunCard({
  run,
  onRename,
  onToggle,
  onRemove,
}: {
  run: PinnedRun;
  onRename: (name: string) => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const [name, setName] = useResettableState(run.name);
  // Saved on blur rather than per keystroke: each save is a request to the server.
  const commit = () => {
    const next = name.trim();
    if (next && next !== run.name) onRename(next);
    else setName(run.name);
  };
  const fewTrades = run.metrics.trades < MIN_TRADES;
  const card = cardOf(run);
  const scope = card.scope(run);
  const direction = card.direction(run);
  const open = openRun(run);

  return (
    <article
      aria-label={`Run ${run.slot}`}
      className={`space-y-2 rounded-xl border border-t-4 border-line bg-panel p-3 ${run.hidden ? "opacity-60" : ""}`}
      style={{ borderTopColor: `var(${runColorVar(run)})` }}
    >
      <div className="flex items-center gap-2">
        <span className="num text-sm text-muted">#{run.slot}</span>
        <Input
          aria-label={`Name of run ${run.slot}`}
          value={name}
          className="h-8"
          onChange={(event) => setName(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
            if (event.key === "Escape") setName(run.name);
          }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-sm">
        <span className="font-mono font-semibold">{runSubject(run)}</span>
        <span className="break-all">{runStrategy(run)}</span>
        {direction && <DirectionBadge direction={direction} />}
      </div>
      <p className="text-xs text-muted">{card.description(run)}</p>
      <p className="num text-xs text-muted">
        {scope && `${scope} · `}
        {run.engine} · {run.start} → {run.end} · return {fmtPct(run.metrics.total_return_pct, 1, true)}
      </p>
      {fewTrades && (
        <p className="text-xs text-warn">Only {run.metrics.trades} trades: too few to trust the metrics.</p>
      )}
      <div className="flex flex-wrap gap-1.5">
        <Link
          to={open.to}
          className="inline-flex items-center rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-panel-2"
        >
          {open.label}
        </Link>
        <Link
          to={`/journal?run=${encodeURIComponent(run.id)}`}
          className="inline-flex items-center rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-panel-2"
        >
          Log a trade
        </Link>
        <Button onClick={onToggle}>{run.hidden ? "Show" : "Hide"}</Button>
        <Button variant="ghost" onClick={onRemove}>
          Remove
        </Button>
      </div>
    </article>
  );
}
