import { toggleEngine } from "../lib/choices";
import { FieldGroup, Notice, ToggleChip } from "./ui";

/** The engines to run: one chip per engine the server offers. */
export function EnginePicker({
  available,
  value,
  onChange,
}: {
  available: readonly string[];
  value: readonly string[];
  onChange: (engines: string[]) => void;
}) {
  return (
    <FieldGroup label="Engines">
      <div className="flex gap-1.5 py-1">
        {available.map((engine) => (
          <ToggleChip
            key={engine}
            active={value.includes(engine)}
            onClick={() => onChange(toggleEngine(value, engine))}
            color="var(--accent)"
          >
            {engine}
          </ToggleChip>
        ))}
      </div>
    </FieldGroup>
  );
}

/** Warns that the Cerebro reference is slow on a big universe. */
export function SlowCerebroNotice() {
  return (
    <Notice>
      Cerebro checks the vectorized engine and is slow: expect about a minute per 20 tickers of 10-year history.
    </Notice>
  );
}
