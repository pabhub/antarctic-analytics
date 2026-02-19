import { formatDateTime, formatNumber } from "../../core/api.js";
import { FeasibilitySnapshotResponse } from "../../core/types.js";
import { stationDisplayName } from "./stations.js";

const CARDINAL_16 = [
  "N", "NNE", "NE", "ENE",
  "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW",
  "W", "WNW", "NW", "NNW",
];

function headingLabel(degrees: number | null | undefined): string {
  if (degrees == null || !Number.isFinite(degrees)) return "n/a";
  const normalized = ((degrees % 360) + 360) % 360;
  const index = Math.floor(((normalized + 11.25) % 360) / 22.5);
  const sector = CARDINAL_16[index] ?? "n/a";
  return `${sector} (${normalized.toFixed(0)}°)`;
}

export function renderMetrics(
  snapshot: FeasibilitySnapshotResponse,
  metricsGridEl: HTMLDivElement,
): void {
  metricsGridEl.innerHTML = "";
  const selected = snapshot.stations.find((station) => station.stationId === snapshot.selectedStationId);
  if (!selected) return;
  const aggregationLabel =
    snapshot.aggregation === "none"
      ? "10-minute source"
      : snapshot.aggregation === "hourly"
        ? "Hourly"
        : snapshot.aggregation === "daily"
          ? "Daily"
          : snapshot.aggregation === "monthly"
            ? "Monthly"
            : snapshot.aggregation;
  const metrics: Array<{ label: string; value: string }> = [
    { label: "Data Points", value: formatNumber(selected.summary.dataPoints, 0) },
    { label: "Coverage", value: selected.summary.coverageRatio == null ? "n/a" : `${(selected.summary.coverageRatio * 100).toFixed(1)}%` },
    { label: "Avg Speed", value: `${formatNumber(selected.summary.avgSpeed)} m/s` },
    { label: "P90 Speed (90th pct)", value: `${formatNumber(selected.summary.p90Speed)} m/s` },
    { label: "Hours ≥ 5 m/s", value: formatNumber(selected.summary.hoursAbove5mps, 1) },
    { label: "WPD Proxy", value: selected.summary.estimatedWindPowerDensity == null ? "n/a" : `${formatNumber(selected.summary.estimatedWindPowerDensity, 1)} W/m²` },
    { label: "Temp Range", value: `${formatNumber(selected.summary.minTemperature)} to ${formatNumber(selected.summary.maxTemperature)} ºC` },
    { label: "Dominant Heading (toward)", value: headingLabel(selected.summary.prevailingDirection) },
    { label: "Avg Pressure", value: `${formatNumber(selected.summary.avgPressure)} hPa` },
    { label: "Latest UTC", value: formatDateTime(selected.summary.latestObservationUtc, "UTC") },
    { label: "Snapshot interval", value: aggregationLabel },
    { label: "Station", value: stationDisplayName(snapshot.selectedStationId, snapshot.selectedStationName) },
  ];
  metrics.forEach((metric, index) => {
    const card = document.createElement("article");
    card.className = index < 4 ? "metric-card emphasis" : "metric-card";
    card.innerHTML = `<h3>${metric.label}</h3><p>${metric.value}</p>`;
    metricsGridEl.appendChild(card);
  });
}

export function renderDecisionGuidance(
  snapshot: FeasibilitySnapshotResponse,
  elements: {
    decisionUpdatedEl: HTMLParagraphElement;
    decisionBadgeEl: HTMLSpanElement;
    decisionWindEl: HTMLParagraphElement;
    decisionQualityEl: HTMLParagraphElement;
    decisionRiskEl: HTMLParagraphElement;
  },
): void {
  const { decisionUpdatedEl, decisionBadgeEl, decisionWindEl, decisionQualityEl, decisionRiskEl } = elements;
  const selected = snapshot.stations.find((station) => station.stationId === snapshot.selectedStationId);
  if (!selected) {
    decisionUpdatedEl.textContent = "Latest UTC n/a";
    decisionBadgeEl.className = "decision-badge";
    decisionBadgeEl.textContent = "Screening";
    decisionWindEl.textContent = "No data yet.";
    decisionQualityEl.textContent = "No data yet.";
    decisionRiskEl.textContent = "No data yet.";
    return;
  }
  const summary = selected.summary;
  const avgSpeed = summary.avgSpeed;
  const p90Speed = summary.p90Speed;
  const coverage = summary.coverageRatio;
  const hoursAbove5 = summary.hoursAbove5mps;
  const latestUtc = summary.latestObservationUtc;
  const dominantDirection = summary.prevailingDirection;
  const dominantHeading = headingLabel(dominantDirection);

  let windSignal = "Wind signal is inconclusive in the currently loaded window. Review the loaded-years comparison to validate interannual consistency.";
  let badgeClass = "decision-badge moderate";
  let badgeText = "Moderate signal";
  if (avgSpeed != null && p90Speed != null) {
    if (avgSpeed >= 7.0 && p90Speed >= 10.0) {
      windSignal = `Strong current-window signal: avg ${avgSpeed.toFixed(2)} m/s, P90 ${p90Speed.toFixed(2)} m/s${dominantDirection != null ? `, dominant heading ${dominantHeading}` : ""}.`;
      badgeClass = "decision-badge strong";
      badgeText = "Strong signal";
    } else if (avgSpeed >= 5.0 && p90Speed >= 8.0) {
      windSignal = `Moderate current-window signal: avg ${avgSpeed.toFixed(2)} m/s, P90 ${p90Speed.toFixed(2)} m/s${dominantDirection != null ? `, dominant heading ${dominantHeading}` : ""}.`;
    } else {
      windSignal = `Low-to-moderate current-window signal: avg ${formatNumber(avgSpeed)} m/s, P90 ${formatNumber(p90Speed)} m/s${dominantDirection != null ? `, dominant heading ${dominantHeading}` : ""}.`;
      badgeClass = "decision-badge low";
      badgeText = "Low signal";
    }
  }

  let quality = `Coverage and data quality require review (${formatNumber(summary.dataPoints, 0)} data points).`;
  if (coverage != null) {
    if (coverage >= 0.9) {
      quality = `Coverage is high (${(coverage * 100).toFixed(1)}%, ${formatNumber(summary.dataPoints, 0)} data points) and suitable for first-pass screening.`;
    } else if (coverage >= 0.7) {
      quality = `Coverage is partial (${(coverage * 100).toFixed(1)}%, ${formatNumber(summary.dataPoints, 0)} data points). Use loaded-years comparison before investment decisions.`;
    } else {
      quality = `Coverage is low (${(coverage * 100).toFixed(1)}%, ${formatNumber(summary.dataPoints, 0)} data points). Extend backfill before decisions.`;
    }
  }

  const riskParts: string[] = [];
  if (hoursAbove5 != null) riskParts.push(`Hours above 5 m/s: ${formatNumber(hoursAbove5, 1)}.`);
  if (summary.maxSpeed != null) riskParts.push(`Observed max speed: ${formatNumber(summary.maxSpeed, 2)} m/s.`);
  if (summary.minTemperature != null || summary.maxTemperature != null) {
    riskParts.push(`Temperature range: ${formatNumber(summary.minTemperature)} to ${formatNumber(summary.maxTemperature)} ºC.`);
  }
  if (summary.avgPressure != null) {
    riskParts.push(`Avg pressure: ${formatNumber(summary.avgPressure, 1)} hPa.`);
  }
  riskParts.push("For go/no-go confidence, rely on the loaded-years comparison block below for interannual spread.");

  decisionBadgeEl.className = badgeClass;
  decisionBadgeEl.textContent = badgeText;
  decisionUpdatedEl.textContent = `Latest UTC ${formatDateTime(latestUtc, "UTC")}.`;
  decisionWindEl.textContent = windSignal;
  decisionQualityEl.textContent = quality;
  decisionRiskEl.textContent = riskParts.join(" ");
}

export function renderSummaryTable(
  snapshot: FeasibilitySnapshotResponse,
  summaryOutputEl: HTMLTableSectionElement,
): void {
  summaryOutputEl.innerHTML = "";
  for (const station of snapshot.stations) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${stationDisplayName(station.stationId, station.stationName)}</td>
      <td>${formatNumber(station.summary.dataPoints, 0)}</td>
      <td>${station.summary.coverageRatio == null ? "n/a" : `${(station.summary.coverageRatio * 100).toFixed(1)}%`}</td>
      <td>${formatNumber(station.summary.avgSpeed)}</td>
      <td>${formatNumber(station.summary.p90Speed)}</td>
      <td>${formatNumber(station.summary.maxSpeed)}</td>
      <td>${station.summary.hoursAbove5mps == null ? "n/a" : station.summary.hoursAbove5mps.toFixed(1)}</td>
      <td>${formatNumber(station.summary.avgTemperature)}</td>
      <td>${station.summary.estimatedWindPowerDensity == null ? "n/a" : station.summary.estimatedWindPowerDensity.toFixed(1)}</td>
      <td>${formatDateTime(station.summary.latestObservationUtc, "UTC")}</td>
    `;
    summaryOutputEl.appendChild(row);
  }
}

export function renderRowsTable(
  snapshot: FeasibilitySnapshotResponse,
  rowsOutputEl: HTMLTableSectionElement,
): void {
  rowsOutputEl.innerHTML = "";
  const selected = snapshot.stations.find((station) => station.stationId === snapshot.selectedStationId);
  if (!selected || selected.data.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan='8'>No data points available for selected station in this window.</td>";
    rowsOutputEl.appendChild(row);
    return;
  }
  const maxDisplayRows = 1500;
  const pointsToRender = selected.data.length > maxDisplayRows ? selected.data.slice(-maxDisplayRows) : selected.data;
  if (selected.data.length > maxDisplayRows) {
    const notice = document.createElement("tr");
    notice.innerHTML = `<td colspan='8'>Showing latest ${maxDisplayRows.toLocaleString()} of ${selected.data.length.toLocaleString()} data points for UI performance. Use export to download full data.</td>`;
    rowsOutputEl.appendChild(notice);
  }
  for (const point of pointsToRender) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${formatDateTime(point.datetime)}</td>
      <td>${formatNumber(point.temperature)}</td>
      <td>${formatNumber(point.pressure)}</td>
      <td>${formatNumber(point.speed)}</td>
      <td>${formatNumber(point.direction)}</td>
      <td>${formatNumber(point.latitude, 5)}</td>
      <td>${formatNumber(point.longitude, 5)}</td>
      <td>${formatNumber(point.altitude, 1)}</td>
    `;
    rowsOutputEl.appendChild(row);
  }
}
