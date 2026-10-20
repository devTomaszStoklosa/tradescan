import { useState, type Dispatch, type SetStateAction } from "react";

/**
 * State that starts as `value` and starts over from it whenever `resetKey` changes (by default `value` itself),
 * e.g. a form draft that follows the form in the URL, or a picked row that follows a new result.
 *
 * The reset happens while rendering, as React recommends for state that follows a prop: an effect would first
 * render the stale state. Other state of the component is kept. `value` must not be a function.
 */
export function useResettableState<T>(value: T, resetKey: unknown = value): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState(value);
  const [shownKey, setShownKey] = useState(resetKey);
  if (!Object.is(shownKey, resetKey)) {
    setShownKey(resetKey);
    setState(value);
  }
  return [state, setState];
}
