import { useState } from "react";

import type { ParamRow } from "../lib/compare";
import type { PinnedRun } from "../lib/runs";
import { RunLabel } from "./RunCard";
import { Button } from "./ui";

/** Inputs of the runs; only the ones that differ unless "Show all" is on. */
export function ParameterDiffTable({ runs, rows }: { runs: PinnedRun[]; rows: ParamRow[] }) {
  const [showAll, setShowAll] = useState(false);
  const differing = rows.filter((row) => row.differs);
  const identical = rows.length - differing.length;
  const shown = showAll ? rows : differing;

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{showAll ? "All parameters" : "Parameters that differ"}</h2>
        {identical > 0 && (
          <div className="flex items-center gap-2 text-sm text-muted">
            {!showAll && <span>{identical} identical hidden</span>}
            <Button variant="ghost" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Only differences" : "Show all"}
            </Button>
          </div>
        )}
      </div>
      {shown.length ? (
        <div className="relative overflow-x-auto rounded-xl border border-line bg-panel">
          <table className="w-full text-sm">
            <caption className="sr-only">Parameters of the pinned runs</caption>
            <thead>
              <tr className="border-b border-line text-xs text-muted">
                <th scope="col" className="sticky left-0 bg-panel px-3 py-2 text-left font-medium">
                  Parameter
                </th>
                {runs.map((run) => (
                  <th key={run.id} scope="col" className="px-3 py-2 text-right font-medium">
                    <RunLabel run={run} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  key={row.key}
                  className={`border-b border-line last:border-0 ${showAll && !row.differs ? "text-muted" : ""}`}
                >
                  {/* Sticky, so on a phone the label stays visible while the runs scroll sideways. */}
                  <th
                    scope="row"
                    className="sticky left-0 min-w-36 bg-panel px-3 py-1.5 text-left font-normal text-muted"
                  >
                    {row.label}
                    {row.unit && <span className="ml-1 text-xs">({row.unit})</span>}
                  </th>
                  {row.values.map((value, index) => (
                    <td key={runs[index]?.id ?? index} className="num px-3 py-1.5 text-right whitespace-nowrap">
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted">
          {runs.length < 2 ? "Show at least two runs to see what differs." : "All shown runs use the same parameters."}
        </p>
      )}
    </section>
  );
}
