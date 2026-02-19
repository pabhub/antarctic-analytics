declare const L: any;

import { clearAuthToken, hasValidAuthToken, startAuthSessionManager } from "./core/api.js";
import { QueryJobCreateResponse, QueryJobStatusResponse, WindFarmParams } from "./core/types.js";
import { redirectToLogin } from "./core/navigation.js";
import {
  clearAuthUser,
  configuredInputTimeZone as configuredInputTimeZoneSetting,
  getStoredAuthUser,
  readStoredWindFarmParams,
} from "./core/settings.js";
import { createOverlayController, renderStationMarkers } from "./features/overlay.js";
import { createPlaybackController } from "./features/playback.js";
import { DashboardCharts } from "./features/dashboard/charts.js";
import { createDashboardState } from "./features/dashboard/dashboard_state.js";
import { getDashboardDomElements } from "./features/dashboard/dom.js";
import { renderDashboardPage } from "./components/dashboard/page.js";
import {
  WorkflowStage,
  bootstrapDashboard,
  downloadExport,
  handleMapStationClick,
  runAnalysisJob,
} from "./features/dashboard/dashboard_actions.js";
import {
  setPlaybackButtonVisual as setPlaybackButtonVisualControl,
  selectedPlaybackDelayMs as selectedPlaybackDelayMsControl,
} from "./features/dashboard/playback_controls.js";
import { PlaybackManager } from "./features/dashboard/playback_manager.js";
import { setQueryProgress as setQueryProgressUi, setQueryProgressAnalyzing as setQueryProgressAnalyzingUi } from "./features/dashboard/progress.js";
import {
  setError as setErrorUi,
  setLoading as setLoadingUi,
  setPlaybackSectionVisible as setPlaybackSectionVisibleUi,
  setResultsSkeletonVisible as setResultsSkeletonVisibleUi,
  setSnapshotSectionsVisible as setSnapshotSectionsVisibleUi,
  setTablesCollapsed as setTablesCollapsedUi,
  setTimeframeSectionVisible as setTimeframeSectionVisibleUi,
  updateChartVisibility as updateChartVisibilityUi,
} from "./features/dashboard/sections.js";
import { TimeframeManager } from "./features/dashboard/timeframe_manager.js";

renderDashboardPage();
startAuthSessionManager();
const dom = getDashboardDomElements();
const state = createDashboardState();

const map = L.map("map-canvas", { zoomControl: false }).setView([-62.7, -60.5], 7);
L.control.zoom({ position: "topright" }).addTo(map);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a> (ODbL)',
}).addTo(map);

const overlayController = createOverlayController(map);
const playbackController = createPlaybackController();
const charts = new DashboardCharts(
  dom.windChartCanvas,
  dom.weatherChartCanvas,
  dom.roseChartCanvas,
  dom.timeframeTrendWrapEl,
  dom.timeframeTrendCanvas,
);

const configuredInputTimeZone = (): string => configuredInputTimeZoneSetting("UTC");
const TOAST_AUTO_HIDE_MS = 4500;
let toastTimerId: number | null = null;

function selectedHistoryYears(): number {
  const parsed = Number.parseInt(dom.historyYearsSelect.value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 2;
}

function windFarmParamsFromStorage(): WindFarmParams | null {
  return readStoredWindFarmParams();
}

function refreshAuthBadge(): void {
  if (!hasValidAuthToken()) {
    dom.authUserEl.textContent = "Not authenticated";
    clearAuthUser();
    return;
  }
  dom.authUserEl.textContent = `Signed in: ${getStoredAuthUser() ?? "Not authenticated"}`;
}

function setWorkflowStage(_stage: WorkflowStage, helperText?: string): void {
  if (helperText) dom.statusEl.textContent = helperText;
}

function ensureAuthenticated(): boolean {
  if (hasValidAuthToken()) return true;
  setWorkflowStage("auth", "Authentication required.");
  redirectToLogin(window.location.pathname);
}

function setPlaybackSectionVisible(visible: boolean): void {
  setPlaybackSectionVisibleUi(dom.mapPlaybackShellEl, dom.playbackProgressWrap, visible);
}

function setTimeframeSectionVisible(visible: boolean): void {
  setTimeframeSectionVisibleUi(dom.timeframeSectionEl, visible);
}

function setSnapshotSectionsVisible(visible: boolean): void {
  setSnapshotSectionsVisibleUi(
    dom.decisionCardEl,
    dom.chartsSectionEl,
    dom.rawCardEl,
    dom.mapPlaybackShellEl,
    dom.playbackProgressWrap,
    dom.timeframeSectionEl,
    visible,
  );
}

function setResultsSkeletonVisible(visible: boolean): void {
  setResultsSkeletonVisibleUi(dom.resultsSkeletonEl, visible);
}

function updateChartVisibility(
  rows: NonNullable<NonNullable<typeof state.snapshotState>["stations"][number]["data"]>,
  hasDirectionData: boolean,
): void {
  updateChartVisibilityUi(
    rows,
    hasDirectionData,
    dom.windChartCardEl,
    dom.weatherChartCardEl,
    dom.roseChartCardEl,
    dom.chartsSectionEl,
    dom.decisionCardEl,
  );
}

function setError(message: string | null): void {
  setErrorUi(dom.errorBannerEl, message);
}

function setLoading(loading: boolean): void {
  setLoadingUi(dom.stationSelect, dom.historyYearsSelect, loading);
}

function selectedStep(): string {
  return dom.playbackStepSelect.value || "1h";
}

function selectedPlaybackDelayMs(): number {
  return selectedPlaybackDelayMsControl(dom.playbackSpeedSelect);
}

function setPlaybackButtonVisual(playing: boolean): void {
  setPlaybackButtonVisualControl(dom.playbackPlayBtn, playing);
}

function setTimeframeStatus(message: string, tone: "info" | "ok" | "error" = "info"): void {
  const show = tone !== "ok" && message.trim().length > 0;
  if (!show) {
    dom.timeframeStatusEl.textContent = "";
    dom.timeframeStatusEl.classList.add("hidden");
    return;
  }
  dom.timeframeStatusEl.classList.remove("hidden");
  dom.timeframeStatusEl.textContent = message;
  dom.timeframeStatusEl.classList.remove("timeframe-status-info", "timeframe-status-ok", "timeframe-status-error");
  if (tone === "error") {
    dom.timeframeStatusEl.classList.add("timeframe-status-error");
    return;
  }
  dom.timeframeStatusEl.classList.add("timeframe-status-info");
}

function setQueryProgress(status: QueryJobCreateResponse | QueryJobStatusResponse): void {
  setQueryProgressUi(
    dom.queryProgressWrap,
    dom.queryProgressBar,
    dom.queryProgressText,
    status,
  );
}

function setQueryProgressAnalyzing(totalMonths: number, message: string): void {
  setQueryProgressAnalyzingUi(
    dom.queryProgressWrap,
    dom.queryProgressBar,
    dom.queryProgressText,
    totalMonths,
    message,
  );
}

function hideToast(): void {
  if (toastTimerId != null) {
    window.clearTimeout(toastTimerId);
    toastTimerId = null;
  }
  dom.toastEl.classList.add("hidden");
}

function showToast(message: string): void {
  if (toastTimerId != null) {
    window.clearTimeout(toastTimerId);
    toastTimerId = null;
  }
  dom.toastTextEl.textContent = message;
  dom.toastEl.classList.remove("hidden");
  toastTimerId = window.setTimeout(() => {
    dom.toastEl.classList.add("hidden");
    toastTimerId = null;
  }, TOAST_AUTO_HIDE_MS);
}

const timeframeManager = new TimeframeManager({
  elements: {
    timeframeGroupingSelect: dom.timeframeGroupingSelect,
    timeframeRunBtn: dom.timeframeRunBtn,
    timeframeCardsEl: dom.timeframeCardsEl,
    timeframePeriodHeaderEl: dom.timeframePeriodHeaderEl,
    timeframeBodyEl: dom.timeframeBodyEl,
    timeframeComparisonEl: dom.timeframeComparisonEl,
    timeframeGenerationEl: dom.timeframeGenerationEl,
  },
  charts,
  configuredInputTimeZone,
  ensureAuthenticated,
  setError,
  setTimeframeSectionVisible,
  setTimeframeStatus,
  getSnapshotState: () => state.snapshotState,
  getBaselineRange: () => ({ start: state.baselineStartLocal, end: state.baselineEndLocal }),
  windFarmParamsFromStorage,
});

const playbackManager = new PlaybackManager({
  elements: {
    playbackWindowLabelEl: dom.playbackWindowLabelEl,
    playbackProgressBar: dom.playbackProgressBar,
    playbackProgressText: dom.playbackProgressText,
    playbackProgressWrap: dom.playbackProgressWrap,
    playbackPlayBtn: dom.playbackPlayBtn,
    playbackSlider: dom.playbackSlider,
    playbackStatusEl: dom.playbackStatusEl,
    overlayTempInput: dom.overlayTempInput,
    overlayPressureInput: dom.overlayPressureInput,
    overlayTrailInput: dom.overlayTrailInput,
    playbackSpeedSelect: dom.playbackSpeedSelect,
    playbackLoopInput: dom.playbackLoopInput,
  },
  playbackController,
  overlayController,
  charts,
  ensureAuthenticated,
  setError,
  setPlaybackSectionVisible,
  updateChartVisibility,
  configuredInputTimeZone,
  selectedStep,
  selectedPlaybackDelayMs,
});

let onMapStationClick: (stationId: string) => void = () => undefined;
const actionsContext = {
  state,
  map,
  overlayController,
  playbackController,
  charts,
  playbackManager,
  timeframeManager,
  elements: {
    stationSelect: dom.stationSelect,
    statusEl: dom.statusEl,
    playbackProgressWrap: dom.playbackProgressWrap,
    queryProgressWrap: dom.queryProgressWrap,
    queryProgressBar: dom.queryProgressBar,
    queryProgressText: dom.queryProgressText,
    playbackWindowLabelEl: dom.playbackWindowLabelEl,
    timeframeCardsEl: dom.timeframeCardsEl,
    timeframeBodyEl: dom.timeframeBodyEl,
    timeframeComparisonEl: dom.timeframeComparisonEl,
    timeframeGenerationEl: dom.timeframeGenerationEl,
    metricsGridEl: dom.metricsGridEl,
    summaryOutputEl: dom.summaryOutputEl,
    rowsOutputEl: dom.rowsOutputEl,
    decisionUpdatedEl: dom.decisionUpdatedEl,
    decisionBadgeEl: dom.decisionBadgeEl,
    decisionWindEl: dom.decisionWindEl,
    decisionQualityEl: dom.decisionQualityEl,
    decisionRiskEl: dom.decisionRiskEl,
  },
  configuredInputTimeZone,
  selectedStep,
  selectedHistoryYears,
  ensureAuthenticated,
  getMapStationClickHandler: () => onMapStationClick,
  setWorkflowStage,
  setPlaybackSectionVisible,
  setTimeframeSectionVisible,
  setSnapshotSectionsVisible,
  setResultsSkeletonVisible,
  updateChartVisibility,
  setError,
  setLoading,
  setPlaybackButtonVisual,
  setQueryProgress,
  setQueryProgressAnalyzing,
  showToast,
};
onMapStationClick = (stationId: string) => {
  void handleMapStationClick(actionsContext, stationId);
};

dom.stationSelect.addEventListener("change", async () => {
  if (!state.bootstrapState) return;
  const selectedStation = dom.stationSelect.value || null;
  renderStationMarkers(map, overlayController, state.bootstrapState.latestSnapshots, state.bootstrapState.stations, selectedStation, onMapStationClick);
  if (!dom.stationSelect.value) {
    dom.statusEl.textContent = "Select station to start analysis.";
    setSnapshotSectionsVisible(false);
    dom.queryProgressWrap.classList.remove("show");
    return;
  }
  if (
    dom.stationSelect.value &&
    (dom.stationSelect.value !== state.lastLoadedStationId || state.lastLoadedHistoryYears !== selectedHistoryYears())
  ) {
    await runAnalysisJob(actionsContext);
  }
});

dom.historyYearsSelect.addEventListener("change", async () => {
  if (!dom.stationSelect.value) return;
  await runAnalysisJob(actionsContext);
});

dom.playbackStepSelect.addEventListener("change", async () => {
  if (!state.snapshotState) return;
  await playbackManager.load(state.snapshotState, state.baselineStartLocal, state.baselineEndLocal);
});

dom.timeframeRunBtn.addEventListener("click", async () => {
  try {
    await timeframeManager.loadAnalytics();
    setWorkflowStage("explore", "Comparison refreshed.");
  } catch (error) {
    setError(error instanceof Error ? error.message : "Unable to run timeframe analysis.");
  }
});

dom.exportCsvButton.addEventListener("click", async () => {
  await downloadExport(actionsContext, "csv");
});
dom.exportParquetButton.addEventListener("click", async () => {
  await downloadExport(actionsContext, "parquet");
});

dom.authLogoutBtn.addEventListener("click", () => {
  clearAuthToken();
  clearAuthUser();
  refreshAuthBadge();
  hideToast();
  redirectToLogin("/login");
});

window.addEventListener("auth:required", () => {
  refreshAuthBadge();
  redirectToLogin(window.location.pathname);
});

const invalidateMapSize = (): void => {
  window.setTimeout(() => {
    map.invalidateSize({ pan: false, animate: false });
  }, 120);
};
window.addEventListener("resize", invalidateMapSize);
window.addEventListener("orientationchange", invalidateMapSize);
window.addEventListener("load", invalidateMapSize);

dom.toggleTablesButton.addEventListener("click", () => {
  const collapsed = !dom.tablesPanelEl.classList.contains("collapsed");
  setTablesCollapsedUi(dom.tablesPanelEl, dom.toggleTablesButton, collapsed);
});
dom.toastCloseBtn.addEventListener("click", hideToast);

playbackManager.configureEvents();
setTablesCollapsedUi(dom.tablesPanelEl, dom.toggleTablesButton, true);
refreshAuthBadge();
hideToast();
setSnapshotSectionsVisible(false);
if (hasValidAuthToken()) {
  setWorkflowStage("scope", "Authenticated. Loading station bootstrap.");
  void bootstrapDashboard(actionsContext);
} else {
  setWorkflowStage("auth", "Sign in to continue.");
  redirectToLogin(window.location.pathname);
}
