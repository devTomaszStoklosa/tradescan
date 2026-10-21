/**
 * The fields of a rotation setup: universe, rebalance, safe asset, benchmark, history, the ranking and weighting rules
 * with their parameters, the holdings and absolute momentum, and the costs. Shared by Rotation and Rotation sweep,
 * which each add their own buttons.
 */
import type { ConfigOut, WatchlistOut } from "../api/client";
import { PERIODS, ROTATION_SECTION } from "../lib/choices";
import type { RotationForm } from "../lib/rotation";
import { SectionFields } from "./ParamFields";
import { GroupHeading, RuleChoiceFields } from "./TradeRuleFields";
import { UniversePicker } from "./UniverseFilters";
import { Field, FieldGroup, Input, Segmented, Select } from "./ui";

const REBALANCES = [
  { value: "weekly" as const, label: "Weekly" },
  { value: "monthly" as const, label: "Monthly" },
];

export function RotationSetupFields<T extends RotationForm>({
  draft,
  onChange,
  config,
  watchlists,
}: {
  draft: T;
  onChange: (draft: T) => void;
  config: ConfigOut;
  watchlists: WatchlistOut[];
}) {
  const set = <K extends keyof RotationForm>(key: K, value: RotationForm[K]) => onChange({ ...draft, [key]: value });
  const watchlistBenchmark = watchlists.find((item) => item.name === draft.universe.watchlist)?.benchmark;
  const rotation = config.sections.find((section) => section.name === ROTATION_SECTION);
  const costs = config.sections.find((section) => section.name === "backtest");

  return (
    <>
      <UniversePicker
        value={draft.universe}
        onChange={(universe) => set("universe", universe)}
        watchlists={watchlists}
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FieldGroup label="Rebalance" hint="At the last close of every week or month">
          <Segmented
            label="Rebalance"
            value={draft.rebalance}
            options={REBALANCES}
            onChange={(rebalance) => set("rebalance", rebalance)}
          />
        </FieldGroup>
        <Field label="Safe asset" hint="Takes the slots of picks with negative absolute momentum; empty for cash">
          <Input
            value={draft.safeAsset}
            placeholder="cash, e.g. TLT"
            onChange={(event) => set("safeAsset", event.target.value.toUpperCase())}
          />
        </Field>
        <Field label="Buy & hold benchmark">
          <Input
            value={draft.benchmark}
            placeholder={watchlistBenchmark ?? config.benchmark}
            onChange={(event) => set("benchmark", event.target.value.toUpperCase())}
          />
        </Field>
        <Field label="History">
          <Select value={draft.period} onChange={(event) => set("period", event.target.value)}>
            <option value="">default ({config.backtest_period})</option>
            {PERIODS.map((period) => (
              <option key={period} value={period}>
                {period}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Picks</h2>
        <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 lg:grid-cols-3">
          <RuleChoiceFields
            heading="Ranking (strongest first)"
            rules={config.ranking_rules}
            value={draft.ranking}
            params={draft.rankingParams}
            onChange={(ranking, rankingParams) => onChange({ ...draft, ranking, rankingParams })}
          />
          {rotation && (
            <div className="space-y-2">
              <GroupHeading>Holdings and absolute momentum</GroupHeading>
              <SectionFields
                section={rotation}
                overrides={draft.settings}
                onChange={(settings) => set("settings", settings)}
                className="grid grid-cols-2 gap-3"
              />
            </div>
          )}
          <RuleChoiceFields
            heading="Weights"
            rules={config.weight_rules}
            value={draft.weighting}
            params={draft.weightingParams}
            onChange={(weighting, weightingParams) => onChange({ ...draft, weighting, weightingParams })}
          />
        </div>
        {costs && (
          <div className="space-y-2">
            <GroupHeading>Costs, metrics and out-of-sample split</GroupHeading>
            <SectionFields
              section={costs}
              overrides={draft.settings}
              onChange={(settings) => set("settings", settings)}
            />
          </div>
        )}
      </section>
    </>
  );
}
