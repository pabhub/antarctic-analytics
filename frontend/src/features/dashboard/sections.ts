import { FeasibilitySnapshotResponse } from "../../core/types.js";

type MeasurementRow = FeasibilitySnapshotResponse["stations"][number]["data"][number];

export function toggleSection(element: HTMLElement, visible: boolean): void {
  element.classList.toggle("hidden", !visible);
}

export function setPlaybackSectionVisible(
  mapPlaybackShellEl: HTMLDivElement,
  playbackProgressWrap: HTMLDivElement,
  visible: boolean,
): void {
  toggleSection(mapPlaybackShellEl, visible);
  if (!visible) playbackProgressWrap.classList.remove("show");
}

export function setTimeframeSectionVisible(timeframeSectionEl: HTMLDivElement, visible: boolean): void {
  toggleSection(timeframeSectionEl, visible);
}

export function setSnapshotSectionsVisible(
  decisionCardEl: HTMLDivElement,
  chartsSectionEl: HTMLDivElement,
  rawCardEl: HTMLDivElement,
  mapPlaybackShellEl: HTMLDivElement,
  playbackProgressWrap: HTMLDivElement,
  timeframeSectionEl: HTMLDivElement,
  visible: boolean,
): void {
  toggleSection(decisionCardEl, visible);
  toggleSection(chartsSectionEl, visible);
  toggleSection(rawCardEl, visible);
  if (!visible) {
    setPlaybackSectionVisible(mapPlaybackShellEl, playbackProgressWrap, false);
    setTimeframeSectionVisible(timeframeSectionEl, false);
  }
}

export function setResultsSkeletonVisible(resultsSkeletonEl: HTMLDivElement, visible: boolean): void {
  toggleSection(resultsSkeletonEl, visible);
}

export function updateChartVisibility(
  rows: MeasurementRow[],
  hasDirectionData: boolean,
  windChartCardEl: HTMLDivElement,
  weatherChartCardEl: HTMLDivElement,
  roseChartCardEl: HTMLDivElement,
  chartsSectionEl: HTMLDivElement,
  decisionCardEl: HTMLDivElement,
): void {
  const hasSpeedData = rows.some((row) => row.speed != null);
  const hasWeatherData = rows.some((row) => row.temperature != null || row.pressure != null);
  toggleSection(windChartCardEl, hasSpeedData);
  toggleSection(weatherChartCardEl, hasWeatherData);
  toggleSection(roseChartCardEl, hasDirectionData);
  const hasAnyChart = hasSpeedData || hasWeatherData || hasDirectionData;
  if (decisionCardEl.classList.contains("hidden")) {
    toggleSection(chartsSectionEl, false);
  } else {
    toggleSection(chartsSectionEl, hasAnyChart);
  }
}

export function setError(errorBannerEl: HTMLParagraphElement, message: string | null): void {
  if (!message) {
    errorBannerEl.textContent = "";
    errorBannerEl.classList.add("hidden");
    return;
  }
  errorBannerEl.textContent = message;
  errorBannerEl.classList.remove("hidden");
}

export function setTablesCollapsed(
  tablesPanelEl: HTMLDivElement,
  toggleTablesButton: HTMLButtonElement,
  collapsed: boolean,
): void {
  tablesPanelEl.classList.toggle("collapsed", collapsed);
  toggleTablesButton.textContent = collapsed ? "Show tables" : "Hide tables";
}

export function setLoading(
  stationSelect: HTMLSelectElement,
  historyYearsSelect: HTMLSelectElement,
  loading: boolean,
): void {
  stationSelect.disabled = loading;
  historyYearsSelect.disabled = loading;
}
