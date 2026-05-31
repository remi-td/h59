function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function localDateKey(value: string | null | undefined): string | null {
  const date = parseTimestamp(value);
  if (!date) {
    return null;
  }
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  if (!date) {
    return "n/a";
  }
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function formatTime(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  if (!date) {
    return "n/a";
  }
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatSleepWindow(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) {
    return "No sleep session";
  }
  return `${formatTime(start)} -> ${formatTime(end)}`;
}

export function formatDurationMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "n/a";
  }
  const minutes = Math.max(0, Math.trunc(value));
  const hours = Math.floor(minutes / 60);
  return `${pad(hours)}:${pad(minutes % 60)}`;
}

export function formatShortDate(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  if (!date) {
    return "n/a";
  }
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
