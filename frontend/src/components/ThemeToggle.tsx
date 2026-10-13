import { useTheme, type ThemeChoice } from "../state/theme";

const NEXT: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
const ICON: Record<ThemeChoice, string> = { system: "◐", light: "☀", dark: "☾" };

export function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  return (
    <button
      type="button"
      onClick={() => setChoice(NEXT[choice])}
      className="inline-flex size-9 items-center justify-center rounded-lg border border-line text-base hover:bg-panel-2"
      title={`Theme: ${choice} (click for ${NEXT[choice]})`}
      aria-label={`Theme: ${choice}. Switch to ${NEXT[choice]}`}
    >
      <span aria-hidden>{ICON[choice]}</span>
    </button>
  );
}
