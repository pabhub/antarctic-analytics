import { FeasibilitySnapshotResponse } from "../../core/types.js";

export type MeasurementRow = FeasibilitySnapshotResponse["stations"][number]["data"][number];
export type NumericStats = { min: number; max: number; avg: number };
export type BucketGranularity = "hour" | "day" | "week" | "month";
export type MetricEnvelope = {
  min: Array<number | null>;
  avg: Array<number | null>;
  max: Array<number | null>;
};
export type AggregatedEnvelopes = {
  labels: string[];
  granularity: BucketGranularity;
  speed: MetricEnvelope;
  temperature: MetricEnvelope;
  pressure: MetricEnvelope;
};

export function parseIsoDate(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function timeSpanDays(labels: string[]): number {
  if (labels.length < 2) return 0;
  const start = parseIsoDate(labels[0]);
  const end = parseIsoDate(labels[labels.length - 1]);
  if (!start || !end) return 0;
  return Math.max(0, (end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000));
}

function formatAxisDateLabel(value: string, spanDays: number, timeZone: string): string {
  const date = parseIsoDate(value);
  if (!date) return "";
  if (spanDays > 540) {
    return new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit", timeZone }).format(date);
  }
  if (spanDays > 120) {
    return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "2-digit", timeZone }).format(date);
  }
  if (spanDays > 14) {
    return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", timeZone }).format(date);
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

export function timeAxisConfig(labels: string[], spanDays: number, timeZone: string): Record<string, unknown> {
  const maxTicksLimit = spanDays > 540 ? 9 : spanDays > 180 ? 10 : spanDays > 30 ? 12 : 16;
  const dense = labels.length > maxTicksLimit * 3;
  return {
    grid: { color: "rgba(148, 163, 184, 0.18)" },
    ticks: {
      autoSkip: true,
      autoSkipPadding: 12,
      sampleSize: Math.min(120, Math.max(30, labels.length)),
      maxTicksLimit,
      maxRotation: dense ? 38 : 0,
      minRotation: 0,
      padding: 6,
      color: "#475569",
      callback: (_: unknown, index: number) => formatAxisDateLabel(labels[index] ?? "", spanDays, timeZone),
    },
    title: { display: true, text: `Time (${timeZone})`, color: "#334155", font: { size: 11, weight: "700" } },
  };
}

function granularityForSpan(spanDays: number): BucketGranularity {
  if (spanDays <= 10) return "hour";
  if (spanDays <= 180) return "day";
  if (spanDays <= 1080) return "week";
  return "month";
}

function floorToGranularity(value: Date, granularity: BucketGranularity): Date {
  const date = new Date(value.getTime());
  if (granularity === "hour") {
    date.setMinutes(0, 0, 0);
    return date;
  }
  if (granularity === "day") {
    date.setHours(0, 0, 0, 0);
    return date;
  }
  if (granularity === "week") {
    const day = date.getDay();
    const shift = (day + 6) % 7;
    date.setDate(date.getDate() - shift);
    date.setHours(0, 0, 0, 0);
    return date;
  }
  date.setDate(1);
  date.setHours(0, 0, 0, 0);
  return date;
}

function envelopeFromBuckets(valuesByBucket: number[][]): MetricEnvelope {
  const min: Array<number | null> = [];
  const avg: Array<number | null> = [];
  const max: Array<number | null> = [];
  valuesByBucket.forEach((values) => {
    if (values.length === 0) {
      min.push(null);
      avg.push(null);
      max.push(null);
      return;
    }
    const low = Math.min(...values);
    const high = Math.max(...values);
    const mean = values.reduce((sum, item) => sum + item, 0) / values.length;
    min.push(Number(low.toFixed(3)));
    avg.push(Number(mean.toFixed(3)));
    max.push(Number(high.toFixed(3)));
  });
  return { min, avg, max };
}

export function aggregateRowsToEnvelopes(rows: MeasurementRow[]): AggregatedEnvelopes {
  const labels = rows.map((row) => row.datetime);
  const spanDays = timeSpanDays(labels);
  const granularity = granularityForSpan(spanDays);
  type BucketAccumulator = { speed: number[]; temperature: number[]; pressure: number[] };
  const buckets = new Map<number, BucketAccumulator>();

  rows.forEach((row) => {
    const date = parseIsoDate(row.datetime);
    if (!date) return;
    const bucketDate = floorToGranularity(date, granularity);
    const key = bucketDate.getTime();
    let accumulator = buckets.get(key);
    if (!accumulator) {
      accumulator = { speed: [], temperature: [], pressure: [] };
      buckets.set(key, accumulator);
    }
    if (typeof row.speed === "number" && Number.isFinite(row.speed)) accumulator.speed.push(row.speed);
    if (typeof row.temperature === "number" && Number.isFinite(row.temperature)) accumulator.temperature.push(row.temperature);
    if (typeof row.pressure === "number" && Number.isFinite(row.pressure)) accumulator.pressure.push(row.pressure);
  });

  const ordered = Array.from(buckets.entries()).sort((left, right) => left[0] - right[0]);
  const bucketLabels = ordered.map(([timestamp]) => new Date(timestamp).toISOString());
  const speedBuckets = ordered.map(([, values]) => values.speed);
  const temperatureBuckets = ordered.map(([, values]) => values.temperature);
  const pressureBuckets = ordered.map(([, values]) => values.pressure);

  return {
    labels: bucketLabels,
    granularity,
    speed: envelopeFromBuckets(speedBuckets),
    temperature: envelopeFromBuckets(temperatureBuckets),
    pressure: envelopeFromBuckets(pressureBuckets),
  };
}

export function envelopeSummary(envelope: MetricEnvelope): NumericStats | null {
  const lows = envelope.min.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const means = envelope.avg.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const highs = envelope.max.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!lows.length && !means.length && !highs.length) return null;
  const min = lows.length ? Math.min(...lows) : means.length ? Math.min(...means) : Math.min(...highs);
  const max = highs.length ? Math.max(...highs) : means.length ? Math.max(...means) : Math.max(...lows);
  const avg = means.length ? (means.reduce((sum, value) => sum + value, 0) / means.length) : (min + max) / 2;
  return { min, max, avg };
}

export function computeNumericStats(values: Array<number | null>): NumericStats | null {
  const numeric = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!numeric.length) return null;
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const avg = numeric.reduce((sum, value) => sum + value, 0) / numeric.length;
  return { min, max, avg };
}

export function granularityLabel(granularity: BucketGranularity): string {
  if (granularity === "hour") return "hourly";
  if (granularity === "day") return "daily";
  if (granularity === "week") return "weekly";
  return "monthly";
}
