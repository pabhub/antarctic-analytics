const inputTimezoneStorageKey = "aemet.input_timezone";

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

function resolvedTimeZone(fallback = "UTC"): string {
  const stored = localStorage.getItem(inputTimezoneStorageKey)?.trim();
  if (stored) {
    try {
      new Intl.DateTimeFormat("en-GB", { timeZone: stored });
      return stored;
    } catch {
      // fallback below
    }
  }
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (browser) {
    try {
      new Intl.DateTimeFormat("en-GB", { timeZone: browser });
      return browser;
    } catch {
      // fallback below
    }
  }
  return fallback;
}

export function formatTooltipValue(value: unknown, digits = 2): string {
  const numeric = asFiniteNumber(value);
  if (numeric == null) return "n/a";
  return numeric.toFixed(digits);
}

export function datasetValueAt(chart: any, datasetIndex: number, dataIndex: number): number | null {
  const dataset = chart?.data?.datasets?.[datasetIndex];
  if (!dataset) return null;
  const data = dataset.data?.[dataIndex];
  if (data != null && typeof data === "object" && "y" in data) {
    return asFiniteNumber((data as { y?: unknown }).y ?? null);
  }
  return asFiniteNumber(data);
}

export function formatTooltipDateTime(value: string, timeZone = resolvedTimeZone()): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const formatted = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(parsed);
  return `${formatted} (${timeZone})`;
}

export function formatTooltipBucketTitle(
  label: string,
  bucketStart?: string,
  bucketEnd?: string,
  timeZone = resolvedTimeZone(),
): string {
  if (!bucketStart || !bucketEnd) return label;
  const start = new Date(bucketStart);
  const end = new Date(bucketEnd);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return label;
  const fmt = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone,
  });
  return `${label} (${fmt.format(start)} - ${fmt.format(end)})`;
}
