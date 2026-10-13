import { useCallback, useState } from "react";

/** localStorage can be missing or throw (private mode, blocked site data): fall back silently. */
export function readStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Not persisted; the in-memory value still applies for this session.
  }
}

export function useStoredState<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => readStorage(key, initial));
  const update = useCallback(
    (next: T) => {
      setValue(next);
      writeStorage(key, next);
    },
    [key],
  );
  return [value, update];
}
