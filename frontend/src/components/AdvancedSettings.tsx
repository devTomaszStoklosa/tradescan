/** Collapsible panel with a page's adjustable settings and signal parameters, built from the API's declarations. */
import type { ParamSpecOut, SettingsSectionOut, SignalOut } from "../api/client";
import { countChanges, describeSignal, withOwner, withValue, type Overrides, type Values } from "../lib/overrides";
import { ParamFields, SectionFields } from "./ParamFields";
import { SignalChip } from "./SignalChip";
import { Button } from "./ui";

const SCORING = "scoring";
const SIGNAL_WEIGHTS = "signal_weights";

function SignalRow({
  signal,
  values,
  onChange,
  weight,
}: {
  signal: SignalOut;
  values: Values;
  onChange: (values: Values) => void;
  weight?: { spec: ParamSpecOut; value: number | undefined; onChange: (value: number | null) => void };
}) {
  const changed = Object.keys(values).length + (weight?.value !== undefined ? 1 : 0);
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-sm hover:bg-panel-2">
        <span className="inline-block text-muted transition group-open:rotate-90" aria-hidden>
          ›
        </span>
        <SignalChip name={signal.name} family={signal.family} />
        <span className="min-w-0 flex-1 text-xs text-muted">{describeSignal(signal, values)}</span>
        {changed > 0 && <span className="text-xs font-medium text-accent">{changed} changed</span>}
      </summary>
      <div className="space-y-3 px-3 pt-1 pb-3">
        <ParamFields specs={signal.params} values={values} onChange={onChange} />
        {weight && (
          <ParamFields
            specs={[weight.spec]}
            values={weight.value === undefined ? {} : { [weight.spec.name]: weight.value }}
            onChange={(next) => weight.onChange((next[weight.spec.name] as number | undefined) ?? null)}
          />
        )}
      </div>
    </details>
  );
}

function SignalParameters({
  signals,
  params,
  onParamsChange,
  scoring,
  settings,
  onSettingsChange,
}: {
  signals: SignalOut[];
  params: Overrides;
  onParamsChange: (params: Overrides) => void;
  scoring?: SettingsSectionOut;
  settings: Overrides;
  onSettingsChange: (settings: Overrides) => void;
}) {
  const weightsSpec = scoring?.params.find((spec) => spec.name === SIGNAL_WEIGHTS);
  const weights = (settings[SCORING]?.[SIGNAL_WEIGHTS] ?? {}) as Record<string, number>;

  const setWeight = (name: string, value: number | null) => {
    if (!weightsSpec) return;
    const next = { ...weights };
    if (value === null) delete next[name];
    else next[name] = value;
    onSettingsChange(withOwner(settings, SCORING, withValue(settings[SCORING] ?? {}, weightsSpec, next)));
  };

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">Signal parameters</h3>
      {signals.length ? (
        <div className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {signals.map((signal) => (
            <SignalRow
              key={signal.name}
              signal={signal}
              values={params[signal.name] ?? {}}
              onChange={(values) => onParamsChange(withOwner(params, signal.name, values))}
              weight={
                weightsSpec && {
                  spec: { ...weightsSpec, name: signal.name, kind: "float", label: "Score weight", unit: "", help: "", default: signal.weight, keys: null },
                  value: weights[signal.name],
                  onChange: (value) => setWeight(signal.name, value),
                }
              }
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted">No signals match the selected families and direction.</p>
      )}
    </section>
  );
}

export function AdvancedSettings({
  sections,
  settings,
  onSettingsChange,
  exclude = {},
  signals,
  signalParams = {},
  onSignalParamsChange,
  signalWeights = false,
}: {
  /** Sections to show, in order. */
  sections: SettingsSectionOut[];
  settings: Overrides;
  onSettingsChange: (settings: Overrides) => void;
  /** Parameters shown elsewhere on the page, by section name. */
  exclude?: Record<string, readonly string[]>;
  signals?: SignalOut[];
  signalParams?: Overrides;
  onSignalParamsChange?: (params: Overrides) => void;
  /** Also offer each signal's score weight (scoring.signal_weights). */
  signalWeights?: boolean;
}) {
  const names = sections.map((section) => section.name);
  const changed = countChanges(settings, names) + countChanges(signalParams);
  const scoring = signalWeights ? sections.find((section) => section.name === SCORING) : undefined;

  const resetAll = () => {
    onSettingsChange(Object.fromEntries(Object.entries(settings).filter(([owner]) => !names.includes(owner))));
    onSignalParamsChange?.({});
  };

  return (
    <details className="group/advanced rounded-xl border border-line bg-panel">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium">
        <span className="inline-block text-muted transition group-open/advanced:rotate-90" aria-hidden>
          ›
        </span>
        <span>Advanced settings</span>
        <span className="text-xs font-normal text-muted">
          {changed ? <span className="text-accent">{changed} changed</span> : "every parameter, defaults from settings.toml"}
        </span>
      </summary>
      <div className="space-y-5 border-t border-line p-4">
        {sections.filter((section) => section.params.some((spec) => !exclude[section.name]?.includes(spec.name))).map((section) => (
          <section key={section.name} className="space-y-2">
            <h3 className="text-sm font-semibold">{section.label}</h3>
            <SectionFields section={section} overrides={settings} onChange={onSettingsChange} exclude={exclude[section.name]} />
          </section>
        ))}
        {signals && onSignalParamsChange && (
          <SignalParameters
            signals={signals}
            params={signalParams}
            onParamsChange={onSignalParamsChange}
            scoring={scoring}
            settings={settings}
            onSettingsChange={onSettingsChange}
          />
        )}
        <div className="flex justify-end">
          <Button variant="ghost" onClick={resetAll} disabled={!changed}>
            Reset all to defaults
          </Button>
        </div>
      </div>
    </details>
  );
}
