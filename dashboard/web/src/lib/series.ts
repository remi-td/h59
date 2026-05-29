export function maxTimestamp(values: Array<string | null | undefined>): string | null {
  const timestamps = values.filter((value): value is string => Boolean(value));
  if (!timestamps.length) {
    return null;
  }
  return timestamps.reduce((latest, current) => (current > latest ? current : latest));
}
