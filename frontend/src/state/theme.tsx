import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { readStorage, writeStorage } from "../lib/storage";

export type ThemeChoice = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "tradescan.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

interface ThemeValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

function resolve(choice: ThemeChoice): ResolvedTheme {
  if (choice === "system") return systemPrefersDark() ? "dark" : "light";
  return choice;
}

/**
 * Applied synchronously (not in an effect) so charts re-rendering for the new theme
 * already read the new CSS variables.
 */
function apply(theme: ResolvedTheme): void {
  document.documentElement.dataset.theme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => readStorage<ThemeChoice>(STORAGE_KEY, "system"));
  const [resolved, setResolved] = useState<ResolvedTheme>(() => {
    const initial = resolve(choice);
    apply(initial);
    return initial;
  });

  const setChoice = useCallback((next: ThemeChoice) => {
    const theme = resolve(next);
    apply(theme);
    writeStorage(STORAGE_KEY, next);
    setChoiceState(next);
    setResolved(theme);
  }, []);

  useEffect(() => {
    if (choice !== "system" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(DARK_QUERY);
    const onChange = () => {
      const theme = resolve("system");
      apply(theme);
      setResolved(theme);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [choice]);

  const value = useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
