import { fetchJson, formatNumber, toApiDateTime } from "../../core/api.js";
import { FeasibilitySnapshotResponse, TimeframeAnalyticsResponse, WindFarmParams } from "../../core/types.js";
import { renderComparison, renderTimeframeCards, renderTimeframeTable } from "../timeframes.js";
import { DashboardCharts } from "./charts.js";
import { yearInConfiguredZone } from "./date_ranges.js";
import { timeframeQueryParams } from "./timeframe_query.js";

type TimeframeElements = {
  timeframeGroupingSelect: HTMLSelectElement;
  timeframeRunBtn: HTMLButtonElement;
  timeframeCardsEl: HTMLDivElement;
  timeframePeriodHeaderEl: HTMLTableCellElement;
  timeframeBodyEl: HTMLTableSectionElement;
  timeframeComparisonEl: HTMLDivElement;
  timeframeGenerationEl: HTMLParagraphElement;
};

type TimeframeManagerDeps = {
  elements: TimeframeElements;
  charts: DashboardCharts;
  configuredInputTimeZone: () => string;
  ensureAuthenticated: () => boolean;
  setError: (message: string | null) => void;
  setTimeframeSectionVisible: (visible: boolean) => void;
  setTimeframeStatus: (message: string, tone?: "info" | "ok" | "error") => void;
  getSnapshotState: () => FeasibilitySnapshotResponse | null;
  getBaselineRange: () => { start: string; end: string };
  windFarmParamsFromStorage: () => WindFarmParams | null;
};

type TimeRange = {
  start: string;
  end: string;
  groupBy: "month" | "season";
};

function extractYearsFromPayload(payload: TimeframeAnalyticsResponse): number[] {
  const years = new Set<number>();
  for (const bucket of payload.buckets) {
    const labelYearMatch = bucket.label.match(/^(\d{4})-/);
    if (labelYearMatch) {
      years.add(Number.parseInt(labelYearMatch[1], 10));
      continue;
    }
    const parsed = new Date(bucket.start);
    if (!Number.isNaN(parsed.getTime())) years.add(parsed.getUTCFullYear());
  }
  return Array.from(years)
    .filter((year) => Number.isFinite(year))
    .sort((a, b) => a - b);
}

function isValidRange(start: string, end: string): boolean {
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return false;
  return startDate < endDate;
}

function periodLabel(groupBy: "month" | "season", count: number): string {
  if (groupBy === "month") return count === 1 ? "month" : "months";
  return count === 1 ? "season" : "seasons";
}

export class TimeframeManager {
  private availableYears: number[] = [];

  constructor(private readonly deps: TimeframeManagerDeps) {}

  private grouping(): "month" | "season" {
    return this.deps.elements.timeframeGroupingSelect.value === "season" ? "season" : "month";
  }

  refreshYearOptions(snapshot: FeasibilitySnapshotResponse | null): void {
    this.availableYears = [];
    const selected = snapshot?.stations.find((station) => station.stationId === snapshot?.selectedStationId) ?? null;
    if (!selected) return;

    const years = new Set<number>();
    const timezone = this.deps.configuredInputTimeZone();
    for (const row of selected.data) {
      const year = yearInConfiguredZone(row.datetime, timezone);
      if (year != null) years.add(year);
    }
    this.availableYears = Array.from(years).sort((a, b) => a - b);
  }

  private effectiveRange(): TimeRange | null {
    const baseline = this.deps.getBaselineRange();
    const start = toApiDateTime(baseline.start).trim();
    const end = toApiDateTime(baseline.end).trim();
    if (!start || !end) return null;
    if (!isValidRange(start, end)) return null;
    return {
      start,
      end,
      groupBy: this.grouping(),
    };
  }

  private async fetchTimeframePayload(
    stationId: string,
    range: TimeRange,
    simulation: WindFarmParams | null,
    forceRefreshOnEmpty = false,
  ): Promise<TimeframeAnalyticsResponse> {
    const params = timeframeQueryParams(range, stationId, this.deps.configuredInputTimeZone(), simulation);
    if (forceRefreshOnEmpty) params.set("forceRefreshOnEmpty", "true");
    return fetchJson<TimeframeAnalyticsResponse>(`/api/analysis/timeframes?${params.toString()}`);
  }

  private mergedYears(payload: TimeframeAnalyticsResponse): number[] {
    const payloadYears = extractYearsFromPayload(payload);
    const merged = new Set<number>([...this.availableYears, ...payloadYears]);
    return Array.from(merged)
      .filter((year) => Number.isFinite(year))
      .sort((a, b) => a - b);
  }

  async loadAnalytics(): Promise<void> {
    if (!this.deps.ensureAuthenticated()) return;
    const snapshot = this.deps.getSnapshotState();
    if (!snapshot) {
      this.deps.setTimeframeStatus("Load a station baseline first, then run timeframe analysis.", "error");
      return;
    }

    this.deps.setError(null);
    this.deps.setTimeframeSectionVisible(true);
    this.deps.elements.timeframeRunBtn.disabled = true;
    const previousButtonLabel = this.deps.elements.timeframeRunBtn.textContent;
    this.deps.elements.timeframeRunBtn.textContent = "Running...";
    this.deps.setTimeframeStatus("Running timeframe analysis on loaded history...", "info");
    this.deps.elements.timeframeGenerationEl.textContent = "Loading timeframe analytics...";

    const range = this.effectiveRange();
    if (!range) {
      this.deps.setError("Loaded history window is invalid. Reload the selected station and try again.");
      this.deps.setTimeframeStatus("Loaded history window is invalid. Reload the selected station and try again.", "error");
      this.deps.elements.timeframeRunBtn.disabled = false;
      this.deps.elements.timeframeRunBtn.textContent = previousButtonLabel;
      return;
    }

    try {
      const simulation = this.deps.windFarmParamsFromStorage();
      let payload = await this.fetchTimeframePayload(snapshot.selectedStationId, range, simulation, false);
      if (!payload.buckets.length) {
        this.deps.setTimeframeStatus(
          `No ${periodLabel(range.groupBy, 2)} summaries cached yet. Loading missing history...`,
          "info",
        );
        payload = await this.fetchTimeframePayload(snapshot.selectedStationId, range, simulation, true);
      }

      if (!payload.buckets.length) {
        this.deps.elements.timeframePeriodHeaderEl.textContent = range.groupBy === "season" ? "Season" : "Month";
        this.deps.elements.timeframeCardsEl.innerHTML = "";
        this.deps.elements.timeframeBodyEl.innerHTML = "";
        this.deps.elements.timeframeComparisonEl.innerHTML = "";
        this.deps.charts.clearTimeframeTrend();
        this.deps.elements.timeframeGenerationEl.textContent = "No observations available for the loaded history window.";
        this.deps.setTimeframeStatus(
          `No ${periodLabel(range.groupBy, 2)} available after loading missing history.`,
          "error",
        );
        return;
      }

      this.deps.elements.timeframePeriodHeaderEl.textContent = payload.groupBy === "season" ? "Season" : "Month";
      this.deps.charts.renderTimeframeTrend(payload);
      renderTimeframeCards(this.deps.elements.timeframeCardsEl, payload);
      renderTimeframeTable(this.deps.elements.timeframeBodyEl, payload);

      const years = this.mergedYears(payload);
      renderComparison(this.deps.elements.timeframeComparisonEl, payload, years);
      this.deps.setTimeframeStatus("", "ok");

      const generationValues = payload.buckets
        .map((bucket) => bucket.estimatedGenerationMwh)
        .filter((value): value is number => value != null && Number.isFinite(value));
      if (!generationValues.length) {
        this.deps.elements.timeframeGenerationEl.textContent =
          "No simulation parameters configured. Set wind farm parameters in Config (including density and operating limits).";
        return;
      }

      const totalGeneration = generationValues.reduce((sum, value) => sum + value, 0);
      this.deps.elements.timeframeGenerationEl.textContent =
        `Estimated generation across loaded history window: ${formatNumber(totalGeneration, 3)} MWh.`;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to run timeframe analysis.";
      this.deps.setError(message);
      this.deps.setTimeframeStatus(message, "error");
      throw error;
    } finally {
      this.deps.elements.timeframeRunBtn.disabled = false;
      this.deps.elements.timeframeRunBtn.textContent = previousButtonLabel;
    }
  }
}
