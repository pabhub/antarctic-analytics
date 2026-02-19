import { formatDateTime, formatNumber } from "../core/api.js";
import { TimeframeAnalyticsResponse } from "../core/types.js";

type SummaryStats = {
  bucketCount: number;
  dataPoints: number;
  minSpeed: number | null;
  avgSpeed: number | null;
  maxSpeed: number | null;
  p90Speed: number | null;
  hoursAbove3mps: number | null;
  hoursAbove5mps: number | null;
  minTemperature: number | null;
  maxTemperature: number | null;
  avgPressure: number | null;
  estimatedGenerationMwh: number | null;
};

type YearSummary = {
  year: number;
  bucketCount: number;
  coverageRatio: number;
  avgSpeed: number | null;
  p90Speed: number | null;
  hoursAbove5mps: number | null;
  generationMwh: number | null;
};

function weightedAverage(values: Array<number | null>, weights: number[]): number | null {
  let sum = 0;
  let weightSum = 0;
  for (let idx = 0; idx < values.length; idx += 1) {
    const value = values[idx];
    const weight = weights[idx];
    if (value == null || !Number.isFinite(value) || !Number.isFinite(weight) || weight <= 0) continue;
    sum += value * weight;
    weightSum += weight;
  }
  if (weightSum <= 0) return null;
  return sum / weightSum;
}

function minValue(values: Array<number | null>): number | null {
  const filtered = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!filtered.length) return null;
  return Math.min(...filtered);
}

function maxValue(values: Array<number | null>): number | null {
  const filtered = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!filtered.length) return null;
  return Math.max(...filtered);
}

function sumValue(values: Array<number | null>): number | null {
  const filtered = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!filtered.length) return null;
  return filtered.reduce((sum, value) => sum + value, 0);
}

function avgValue(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function summarize(payload: TimeframeAnalyticsResponse): SummaryStats {
  const weights = payload.buckets.map((bucket) => Math.max(0, bucket.dataPoints));
  const totalRows = weights.reduce((sum, value) => sum + value, 0);
  return {
    bucketCount: payload.buckets.length,
    dataPoints: totalRows,
    minSpeed: minValue(payload.buckets.map((bucket) => bucket.minSpeed)),
    avgSpeed: weightedAverage(payload.buckets.map((bucket) => bucket.avgSpeed), weights),
    maxSpeed: maxValue(payload.buckets.map((bucket) => bucket.maxSpeed)),
    p90Speed: weightedAverage(payload.buckets.map((bucket) => bucket.p90Speed), weights),
    hoursAbove3mps: sumValue(payload.buckets.map((bucket) => bucket.hoursAbove3mps)),
    hoursAbove5mps: sumValue(payload.buckets.map((bucket) => bucket.hoursAbove5mps)),
    minTemperature: minValue(payload.buckets.map((bucket) => bucket.minTemperature)),
    maxTemperature: maxValue(payload.buckets.map((bucket) => bucket.maxTemperature)),
    avgPressure: weightedAverage(payload.buckets.map((bucket) => bucket.avgPressure), weights),
    estimatedGenerationMwh: sumValue(payload.buckets.map((bucket) => bucket.estimatedGenerationMwh)),
  };
}

function metricValue(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return value.toFixed(digits);
}

const MONTH_LABELS: Record<string, string> = {
  "01": "Jan",
  "02": "Feb",
  "03": "Mar",
  "04": "Apr",
  "05": "May",
  "06": "Jun",
  "07": "Jul",
  "08": "Aug",
  "09": "Sep",
  "10": "Oct",
  "11": "Nov",
  "12": "Dec",
};

function displayBucketKey(key: string, groupBy: string): string {
  if (groupBy === "month") return MONTH_LABELS[key] ?? key;
  return key;
}

const MONTH_KEYS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const SEASON_KEYS = ["DJF", "MAM", "JJA", "SON"];

type YearBucket = TimeframeAnalyticsResponse["buckets"][number] & { __year: number; __key: string };

function parseYearAndKey(
  bucket: TimeframeAnalyticsResponse["buckets"][number],
  groupBy: "month" | "season",
): { year: number | null; key: string } {
  if (groupBy === "month") {
    const labelMatch = bucket.label.match(/^(\d{4})-(\d{2})$/);
    if (labelMatch) {
      return {
        year: Number.parseInt(labelMatch[1], 10),
        key: labelMatch[2],
      };
    }
    const parsedStart = new Date(bucket.start);
    if (!Number.isNaN(parsedStart.getTime())) {
      return {
        year: parsedStart.getUTCFullYear(),
        key: String(parsedStart.getUTCMonth() + 1).padStart(2, "0"),
      };
    }
    return { year: null, key: bucket.label };
  }

  const seasonMatch = bucket.label.match(/^(\d{4})-(DJF|MAM|JJA|SON)$/);
  if (seasonMatch) {
    return {
      year: Number.parseInt(seasonMatch[1], 10),
      key: seasonMatch[2],
    };
  }
  const fallbackSeason = bucket.label.match(/(DJF|MAM|JJA|SON)$/);
  return { year: null, key: fallbackSeason?.[1] ?? bucket.label };
}

function summarizeYearBuckets(buckets: YearBucket[]): {
  avgSpeed: number | null;
  p90Speed: number | null;
  hoursAbove5mps: number | null;
  generationMwh: number | null;
} {
  const weights = buckets.map((bucket) => Math.max(0, bucket.dataPoints));
  return {
    avgSpeed: weightedAverage(buckets.map((bucket) => bucket.avgSpeed), weights),
    p90Speed: weightedAverage(buckets.map((bucket) => bucket.p90Speed), weights),
    hoursAbove5mps: sumValue(buckets.map((bucket) => bucket.hoursAbove5mps)),
    generationMwh: sumValue(buckets.map((bucket) => bucket.estimatedGenerationMwh)),
  };
}

function buildYearSummaries(
  years: number[],
  expectedKeys: string[],
  bucketsByYear: Map<number, YearBucket[]>,
): YearSummary[] {
  return years.map((year) => {
    const buckets = bucketsByYear.get(year) ?? [];
    const summary = summarizeYearBuckets(buckets);
    return {
      year,
      bucketCount: buckets.length,
      coverageRatio: expectedKeys.length > 0 ? buckets.length / expectedKeys.length : 0,
      avgSpeed: summary.avgSpeed,
      p90Speed: summary.p90Speed,
      hoursAbove5mps: summary.hoursAbove5mps,
      generationMwh: summary.generationMwh,
    };
  });
}

function range(values: number[]): { min: number; max: number } | null {
  if (!values.length) return null;
  return {
    min: Math.min(...values),
    max: Math.max(...values),
  };
}

function decisionFromYearSummaries(
  yearSummaries: YearSummary[],
  overallSummary: SummaryStats,
  groupBy: "month" | "season",
): {
  badgeClass: string;
  badgeText: string;
  windComment: string;
  qualityComment: string;
  riskComment: string;
} {
  const validAvgSpeeds = yearSummaries
    .map((year) => year.avgSpeed)
    .filter((value): value is number => value != null && Number.isFinite(value));
  const validP90Speeds = yearSummaries
    .map((year) => year.p90Speed)
    .filter((value): value is number => value != null && Number.isFinite(value));
  const coverageStrongYears = yearSummaries.filter((year) => year.coverageRatio >= 0.75).length;
  const avgCoverage = avgValue(yearSummaries.map((year) => year.coverageRatio)) ?? 0;

  const meanAvgSpeed = avgValue(validAvgSpeeds);
  const meanP90Speed = avgValue(validP90Speeds);
  const speedRange = range(validAvgSpeeds);
  const strongestYear = yearSummaries
    .filter((year): year is YearSummary & { avgSpeed: number } => year.avgSpeed != null && Number.isFinite(year.avgSpeed))
    .sort((a, b) => b.avgSpeed - a.avgSpeed)[0];
  const weakestYear = yearSummaries
    .filter((year): year is YearSummary & { avgSpeed: number } => year.avgSpeed != null && Number.isFinite(year.avgSpeed))
    .sort((a, b) => a.avgSpeed - b.avgSpeed)[0];

  let badgeClass = "decision-badge moderate";
  let badgeText = "Moderate signal";
  if (meanAvgSpeed != null && meanP90Speed != null) {
    if (meanAvgSpeed >= 7.0 && meanP90Speed >= 10.0) {
      badgeClass = "decision-badge strong";
      badgeText = "Strong signal";
    } else if (meanAvgSpeed < 5.0 || meanP90Speed < 8.0) {
      badgeClass = "decision-badge low";
      badgeText = "Low signal";
    }
  }

  const windCommentParts: string[] = [];
  windCommentParts.push(
    `Loaded-year mean wind is ${formatNumber(meanAvgSpeed)} m/s with mean P90 ${formatNumber(meanP90Speed)} m/s.`,
  );
  if (strongestYear && weakestYear && strongestYear.year !== weakestYear.year) {
    windCommentParts.push(
      `Best year ${strongestYear.year}: ${formatNumber(strongestYear.avgSpeed)} m/s vs weakest ${weakestYear.year}: ${formatNumber(weakestYear.avgSpeed)} m/s.`,
    );
  }
  if (speedRange != null) {
    const spread = speedRange.max - speedRange.min;
    if (spread >= 1.5) {
      windCommentParts.push("Interannual wind spread is high, so yield assumptions should include conservative P50/P90 cases.");
    } else {
      windCommentParts.push("Interannual wind spread is moderate, indicating a relatively stable multi-year signal.");
    }
  }

  const qualityCommentParts: string[] = [];
  qualityCommentParts.push(
    `Coverage across loaded years averages ${(avgCoverage * 100).toFixed(1)}% of expected ${groupBy} buckets.`,
  );
  qualityCommentParts.push(`Years with strong bucket coverage: ${coverageStrongYears}/${yearSummaries.length}.`);
  qualityCommentParts.push(`Missing year/${groupBy} cells are displayed as "-".`);

  const generationYears = yearSummaries.filter((year) => year.generationMwh != null && Number.isFinite(year.generationMwh)).length;
  const riskCommentParts: string[] = [];
  riskCommentParts.push(
    `Observed speed envelope in loaded scope: ${formatNumber(overallSummary.minSpeed)} to ${formatNumber(overallSummary.maxSpeed)} m/s.`,
  );
  riskCommentParts.push(
    `Temperature range: ${formatNumber(overallSummary.minTemperature)} to ${formatNumber(overallSummary.maxTemperature)} ºC.`,
  );
  if (generationYears === 0) {
    riskCommentParts.push("Generation comparison requires simulation parameters in Config.");
  } else {
    riskCommentParts.push(`Generation is available for ${generationYears}/${yearSummaries.length} loaded years.`);
  }

  return {
    badgeClass,
    badgeText,
    windComment: windCommentParts.join(" "),
    qualityComment: qualityCommentParts.join(" "),
    riskComment: riskCommentParts.join(" "),
  };
}

export function renderTimeframeCards(
  container: HTMLDivElement,
  payload: TimeframeAnalyticsResponse,
): void {
  container.innerHTML = "";
  const summary = summarize(payload);
  const dominant = payload.windRose.dominantSector ?? "n/a";
  const concentration = payload.windRose.directionalConcentration == null
    ? "n/a"
    : `${(payload.windRose.directionalConcentration * 100).toFixed(1)}%`;

  const cards = [
    `
      <h4>Selected Scope</h4>
      <p>${formatDateTime(payload.requestedStart)} → ${formatDateTime(payload.requestedEnd)}</p>
      <p>Grouping: ${payload.groupBy} · Buckets: ${summary.bucketCount} · Rows: ${summary.dataPoints}</p>
      <p>Dominant direction: ${dominant} · Concentration: ${concentration}</p>
    `,
    `
      <h4>Wind Performance</h4>
      <p>Speed min/avg/max: ${formatNumber(summary.minSpeed)} / ${formatNumber(summary.avgSpeed)} / ${formatNumber(summary.maxSpeed)} m/s</p>
      <p>P90 speed: ${formatNumber(summary.p90Speed)} m/s</p>
      <p>Hours ≥ 3 m/s: ${formatNumber(summary.hoursAbove3mps)} · Hours ≥ 5 m/s: ${formatNumber(summary.hoursAbove5mps)}</p>
    `,
    `
      <h4>Environment + Yield</h4>
      <p>Temp range: ${formatNumber(summary.minTemperature)} to ${formatNumber(summary.maxTemperature)} ºC</p>
      <p>Avg pressure: ${formatNumber(summary.avgPressure)} hPa</p>
      <p>Estimated generation: ${formatNumber(summary.estimatedGenerationMwh)} MWh</p>
    `,
  ];

  for (const html of cards) {
    const card = document.createElement("article");
    card.className = "timeframe-card";
    card.innerHTML = html;
    container.appendChild(card);
  }
}

export function renderTimeframeTable(
  tbody: HTMLTableSectionElement,
  payload: TimeframeAnalyticsResponse,
): void {
  tbody.innerHTML = "";
  for (const bucket of payload.buckets) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${bucket.label}</td>
      <td>${formatDateTime(bucket.start)}</td>
      <td>${formatDateTime(bucket.end)}</td>
      <td>${bucket.dataPoints}</td>
      <td>${formatNumber(bucket.minSpeed)}</td>
      <td>${formatNumber(bucket.avgSpeed)}</td>
      <td>${formatNumber(bucket.maxSpeed)}</td>
      <td>${formatNumber(bucket.p90Speed)}</td>
      <td>${formatNumber(bucket.hoursAbove3mps)}</td>
      <td>${formatNumber(bucket.hoursAbove5mps)}</td>
      <td>${formatNumber(bucket.speedVariability)}</td>
      <td>${formatNumber(bucket.dominantDirection)}</td>
      <td>${formatNumber(bucket.avgTemperature)}</td>
      <td>${formatNumber(bucket.avgPressure)}</td>
      <td>${formatNumber(bucket.estimatedGenerationMwh)}</td>
    `;
    tbody.appendChild(row);
  }
}

export function renderComparison(
  container: HTMLDivElement,
  selectedPayload: TimeframeAnalyticsResponse,
  loadedYears: number[] = [],
): void {
  container.innerHTML = "";

  const groupBy = selectedPayload.groupBy === "season" ? "season" : "month";
  const expectedKeys = groupBy === "season" ? SEASON_KEYS : MONTH_KEYS;
  const parsedBuckets: YearBucket[] = [];
  const yearsSet = new Set<number>(loadedYears);

  for (const bucket of selectedPayload.buckets) {
    const parsed = parseYearAndKey(bucket, groupBy);
    if (parsed.year == null) continue;
    yearsSet.add(parsed.year);
    parsedBuckets.push({ ...bucket, __year: parsed.year, __key: parsed.key });
  }

  const years = Array.from(yearsSet)
    .filter((year) => Number.isFinite(year))
    .sort((a, b) => a - b);

  if (!years.length) {
    container.textContent = "No loaded years available for comparison.";
    return;
  }

  const yearAndKeyToBucket = new Map<string, YearBucket>();
  const bucketsByYear = new Map<number, YearBucket[]>();
  for (const bucket of parsedBuckets) {
    yearAndKeyToBucket.set(`${bucket.__year}|${bucket.__key}`, bucket);
    const existing = bucketsByYear.get(bucket.__year) ?? [];
    existing.push(bucket);
    bucketsByYear.set(bucket.__year, existing);
  }
  const yearSummaries = buildYearSummaries(years, expectedKeys, bucketsByYear);
  const overallSummary = summarize(selectedPayload);
  const decision = decisionFromYearSummaries(yearSummaries, overallSummary, groupBy);

  const yearSummaryRows = yearSummaries.map((summary) => {
    return `
      <tr>
        <td>${summary.year}</td>
        <td>${summary.bucketCount}/${expectedKeys.length}</td>
        <td>${metricValue(summary.avgSpeed)}</td>
        <td>${metricValue(summary.p90Speed)}</td>
        <td>${metricValue(summary.hoursAbove5mps)}</td>
        <td>${metricValue(summary.generationMwh, 3)}</td>
      </tr>
    `;
  }).join("");

  const bucketRows = expectedKeys.map((bucketKey) => {
    const cells = years.map((year) => {
      const bucket = yearAndKeyToBucket.get(`${year}|${bucketKey}`);
      if (!bucket) {
        return `
          <td class="comparison-missing">-</td>
          <td class="comparison-missing">-</td>
          <td class="comparison-missing">-</td>
          <td class="comparison-missing">-</td>
        `;
      }
      return `
        <td>${metricValue(bucket.avgSpeed)}</td>
        <td>${metricValue(bucket.p90Speed)}</td>
        <td>${metricValue(bucket.hoursAbove5mps)}</td>
        <td>${metricValue(bucket.estimatedGenerationMwh, 3)}</td>
      `;
    }).join("");
    return `
      <tr>
        <td>${displayBucketKey(bucketKey, groupBy)}</td>
        ${cells}
      </tr>
    `;
  }).join("");

  const yearHeader = years
    .map((year) => `<th colspan="4">${year}</th>`)
    .join("");
  const metricHeader = years
    .map(() => "<th>Avg</th><th>P90</th><th>Hrs ≥ 5</th><th>Gen (MWh)</th>")
    .join("");

  const wrap = document.createElement("article");
  wrap.className = "comparison-summary";
  wrap.innerHTML = `
    <h4>${groupBy === "month" ? "Monthly" : "Seasonal"} comparison across loaded years</h4>
    <p class="muted">
      Loaded years: ${years.join(", ")}.
      Missing year/bucket combinations are shown as "-".
    </p>
    <section class="comparison-decision">
      <div class="comparison-decision-head">
        <span class="${decision.badgeClass}">${decision.badgeText}</span>
        <p class="muted">Decision comments are derived from loaded-year ${groupBy} buckets and current simulation settings.</p>
      </div>
      <div class="comparison-decision-grid">
        <article class="comparison-decision-tile">
          <h5>Wind Resource Signal</h5>
          <p>${decision.windComment}</p>
        </article>
        <article class="comparison-decision-tile">
          <h5>Data Quality & Coverage</h5>
          <p>${decision.qualityComment}</p>
        </article>
        <article class="comparison-decision-tile">
          <h5>Operational Implications</h5>
          <p>${decision.riskComment}</p>
        </article>
      </div>
    </section>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Year</th>
            <th>Coverage</th>
            <th>Avg Speed</th>
            <th>P90 Speed</th>
            <th>Hours ≥ 5</th>
            <th>Generation (MWh)</th>
          </tr>
        </thead>
        <tbody>${yearSummaryRows}</tbody>
      </table>
    </div>
    <div class="table-wrap table-group">
      <table>
        <thead>
          <tr>
            <th>${groupBy === "month" ? "Month" : "Season"}</th>
            ${yearHeader}
          </tr>
          <tr>
            <th>Metric</th>
            ${metricHeader}
          </tr>
        </thead>
        <tbody>${bucketRows}</tbody>
      </table>
    </div>
  `;
  container.appendChild(wrap);
}
