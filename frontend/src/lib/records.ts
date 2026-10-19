/** `record` without `key`; the record itself is left as it is. */
export function omit<T>(record: Readonly<Record<string, T>>, key: string): Record<string, T> {
  const { [key]: _omitted, ...rest } = record;
  return rest;
}
