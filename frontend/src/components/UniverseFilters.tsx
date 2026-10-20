/** Inputs shared by the scan and edge forms: watchlist or tickers, direction and signal families. */
import type { Family, WatchlistOut } from "../api/client";
import type { DirectionChoice, Universe } from "../lib/params";
import { FAMILY_LABELS, familyColor } from "./SignalChip";
import { Field, FieldGroup, Input, Segmented, Select, ToggleChip } from "./ui";

const CUSTOM = "__custom__";

export function UniversePicker({
  value,
  onChange,
  watchlists,
}: {
  value: Universe;
  onChange: (value: Universe) => void;
  watchlists: WatchlistOut[];
}) {
  const custom = !value.watchlist;
  const selected = watchlists.find((item) => item.name === value.watchlist);
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
      <Field label="Universe">
        <Select
          value={custom ? CUSTOM : value.watchlist}
          onChange={(event) =>
            onChange(
              event.target.value === CUSTOM
                ? { watchlist: "", tickers: value.tickers }
                : { watchlist: event.target.value, tickers: value.tickers },
            )
          }
        >
          {watchlists.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name} ({item.tickers.length})
            </option>
          ))}
          <option value={CUSTOM}>Custom tickers…</option>
        </Select>
      </Field>
      {custom ? (
        <Field label="Tickers" hint="Yahoo symbols, e.g. AAPL, PKO.WA, BTC-USD">
          <Input
            value={value.tickers}
            placeholder="AAPL, MSFT, PKO.WA"
            onChange={(event) => onChange({ watchlist: "", tickers: event.target.value })}
          />
        </Field>
      ) : (
        <FieldGroup label="Tickers">
          <p className="truncate py-2 text-sm font-normal text-fg" title={selected?.tickers.join(", ")}>
            {selected?.tickers.join(", ")}
            {selected?.benchmark && <span className="text-muted"> · benchmark {selected.benchmark}</span>}
          </p>
        </FieldGroup>
      )}
    </div>
  );
}

export function DirectionPicker({
  value,
  onChange,
}: {
  value: DirectionChoice;
  onChange: (value: DirectionChoice) => void;
}) {
  return (
    <FieldGroup label="Direction">
      <Segmented
        label="Direction"
        value={value}
        onChange={onChange}
        options={[
          { value: "both", label: "Both" },
          { value: "long", label: "Long" },
          { value: "short", label: "Short" },
        ]}
      />
    </FieldGroup>
  );
}

export function FamilyPicker({
  value,
  onChange,
  families,
}: {
  value: Family[];
  onChange: (value: Family[]) => void;
  families: Family[];
}) {
  const toggle = (family: Family) =>
    onChange(value.includes(family) ? value.filter((item) => item !== family) : [...value, family]);
  return (
    <FieldGroup label={value.length ? "Families" : "Families (all)"}>
      <div className="flex flex-wrap gap-1.5 py-1">
        {families.map((family) => (
          <ToggleChip
            key={family}
            active={value.includes(family)}
            onClick={() => toggle(family)}
            color={familyColor(family)}
          >
            {FAMILY_LABELS[family]}
          </ToggleChip>
        ))}
      </div>
    </FieldGroup>
  );
}
