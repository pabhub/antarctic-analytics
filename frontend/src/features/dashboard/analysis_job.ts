import { fetchJson, toDateTimeLocalInZone } from "../../core/api.js";
import { FeasibilitySnapshotResponse, QueryJobCreateResponse, QueryJobStatusResponse } from "../../core/types.js";
import { clearPlaybackTrail, renderStationMarkers } from "../overlay.js";
import { computeBaselineStart as computeBaselineStartFromHistory, selectedStationLatestDate as selectedStationLatestDateFromHistory } from "./history.js";
import { selectedMeasurementTypes } from "./measurement_types.js";
import { renderDecisionGuidance, renderMetrics, renderRowsTable, renderSummaryTable } from "./renderers.js";
import { stationDisplayName } from "./stations.js";
import { DashboardActionsContext, LatestAvailabilityPayload } from "./actions_types.js";

const QUERY_JOB_POLL_INTERVAL_MS = 4_000;

function snapshotAggregationForHistoryYears(years: number): "hourly" | "daily" {
  if (years <= 2) return "hourly";
  return "daily";
}

function selectedStationLatestDate(ctx: DashboardActionsContext, stationId: string): Date | null {
  return selectedStationLatestDateFromHistory(ctx.state.bootstrapState, stationId);
}

function computeBaselineStart(ctx: DashboardActionsContext, stationId: string, years: number): string {
  return computeBaselineStartFromHistory(
    ctx.state.bootstrapState,
    stationId,
    years,
    toDateTimeLocalInZone,
    ctx.configuredInputTimeZone(),
  );
}

async function pollQueryJob(ctx: DashboardActionsContext, jobId: string): Promise<QueryJobStatusResponse> {
  while (true) {
    const status = await fetchJson<QueryJobStatusResponse>(`/api/analysis/query-jobs/${jobId}`);
    ctx.setQueryProgress(status);
    if (status.status === "failed") throw new Error(status.errorDetail ?? "Query job failed.");
    if (status.status === "complete") return status;
    await new Promise((resolve) => window.setTimeout(resolve, QUERY_JOB_POLL_INTERVAL_MS));
  }
}

export async function handleMapStationClick(ctx: DashboardActionsContext, stationIdClicked: string): Promise<void> {
  if (!ctx.state.bootstrapState) return;
  const selectedProfile = ctx.state.bootstrapState.stations.find((item) => item.stationId === stationIdClicked);
  const primaryId = selectedProfile?.primaryStationId ?? stationIdClicked;
  if (!ctx.state.bootstrapState.selectableStationIds.includes(primaryId)) return;
  const years = ctx.selectedHistoryYears();
  const alreadyLoaded = (
    primaryId === ctx.state.lastLoadedStationId &&
    ctx.state.snapshotState?.selectedStationId === primaryId &&
    ctx.state.lastLoadedHistoryYears === years
  );
  ctx.elements.stationSelect.value = primaryId;
  renderStationMarkers(
    ctx.map,
    ctx.overlayController,
    ctx.state.bootstrapState.latestSnapshots,
    ctx.state.bootstrapState.stations,
    primaryId,
    ctx.getMapStationClickHandler(),
  );
  if (alreadyLoaded) {
    ctx.elements.statusEl.textContent =
      `Using cached history for ${stationDisplayName(primaryId, selectedProfile?.stationName)} (${years} years).`;
    return;
  }
  await runAnalysisJob(ctx);
}

export async function runAnalysisJob(ctx: DashboardActionsContext): Promise<void> {
  if (!ctx.ensureAuthenticated()) return;
  if (!ctx.state.bootstrapState) return;
  const station = ctx.elements.stationSelect.value;
  const historyYears = ctx.selectedHistoryYears();
  if (!station) {
    ctx.setError("Select an Antarctic station before loading baseline.");
    return;
  }

  const stationName = stationDisplayName(
    station,
    ctx.state.bootstrapState.stations.find((item) => item.stationId === station)?.stationName,
  );
  const snapshotAggregation = snapshotAggregationForHistoryYears(historyYears);
  ctx.setError(null);
  ctx.setWorkflowStage("fetch", `Loading ${historyYears}-year station history using cache-first retrieval.`);
  ctx.setSnapshotSectionsVisible(false);
  ctx.setPlaybackSectionVisible(false);
  ctx.setTimeframeSectionVisible(false);
  ctx.setResultsSkeletonVisible(false);
  ctx.playbackController.pause();
  ctx.setPlaybackButtonVisual(false);
  clearPlaybackTrail(ctx.overlayController);
  ctx.charts.resetAll();
  ctx.elements.queryProgressWrap.classList.remove("show");
  ctx.elements.playbackProgressWrap.classList.remove("show");
  ctx.elements.timeframeCardsEl.innerHTML = "";
  ctx.elements.timeframeComparisonEl.innerHTML = "";
  ctx.charts.clearTimeframeTrend();
  ctx.elements.timeframeGenerationEl.textContent = "";

  const latestForStation = selectedStationLatestDate(ctx, station);
  let resolvedLatest = latestForStation;
  if (!resolvedLatest) {
    try {
      const availability = await fetchJson<LatestAvailabilityPayload>(
        `/api/metadata/latest-availability/station/${encodeURIComponent(station)}`,
      );
      if (ctx.state.bootstrapState) {
        ctx.state.bootstrapState.latestObservationByStation[station] = availability.newest_observation_utc;
        if (availability.suggested_start_utc) {
          ctx.state.bootstrapState.suggestedStartByStation[station] = availability.suggested_start_utc;
        }
      }
      if (availability.newest_observation_utc) {
        const parsed = new Date(availability.newest_observation_utc);
        if (!Number.isNaN(parsed.getTime())) resolvedLatest = parsed;
      }
    } catch (error) {
      ctx.setError(error instanceof Error ? error.message : "Unable to resolve latest station availability.");
      return;
    }
  }
  if (!resolvedLatest) {
    ctx.setError("Latest station availability is unknown for this station in the configured lookback horizon.");
    return;
  }

  ctx.state.baselineStartLocal = computeBaselineStart(ctx, station, historyYears);
  ctx.state.baselineEndLocal = toDateTimeLocalInZone(resolvedLatest, ctx.configuredInputTimeZone());
  if (!ctx.state.baselineStartLocal || !ctx.state.baselineEndLocal) {
    ctx.setError("Unable to compute baseline date range for this station.");
    return;
  }
  ctx.playbackManager.syncStepOptionsForRange(ctx.state.baselineStartLocal, ctx.state.baselineEndLocal);

  const payloadBody: Record<string, unknown> = {
    station,
    start: ctx.state.baselineStartLocal,
    end: ctx.state.baselineEndLocal,
    location: ctx.configuredInputTimeZone(),
    playbackStep: ctx.selectedStep(),
    aggregation: snapshotAggregation,
    types: selectedMeasurementTypes(),
  };

  ctx.setResultsSkeletonVisible(true);
  ctx.elements.queryProgressWrap.classList.add("show");
  ctx.setLoading(true);
  try {
    const created = await fetchJson<QueryJobCreateResponse>("/api/analysis/query-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadBody),
    });
    ctx.setQueryProgress(created);
    ctx.elements.statusEl.textContent = `Loading ${stationName} history (${historyYears} years, ${snapshotAggregation} snapshot).`;

    const completedJobStatus = await pollQueryJob(ctx, created.jobId);
    ctx.setQueryProgressAnalyzing(completedJobStatus.totalWindows, "Data loaded. Analyzing data...");
    ctx.elements.statusEl.textContent = `Analyzing ${stationName} data...`;
    const snapshot = await fetchJson<FeasibilitySnapshotResponse>(`/api/analysis/query-jobs/${created.jobId}/result`);
    ctx.state.snapshotState = snapshot;
    ctx.state.lastLoadedStationId = snapshot.selectedStationId;
    ctx.state.lastLoadedHistoryYears = historyYears;
    ctx.state.baselineEndLocal = toDateTimeLocalInZone(new Date(snapshot.effectiveEnd), ctx.configuredInputTimeZone());
    ctx.playbackManager.syncStepOptionsForRange(ctx.state.baselineStartLocal, ctx.state.baselineEndLocal);
    const selected = snapshot.stations.find((stationItem) => stationItem.stationId === snapshot.selectedStationId);
    const hasSelectedRows = (selected?.data.length ?? 0) > 0;
    if (!hasSelectedRows) {
      ctx.setError("No data points available for the selected station in the loaded baseline.");
      ctx.elements.statusEl.textContent = "No baseline data available for selected station.";
      ctx.elements.queryProgressWrap.classList.remove("show");
      return;
    }

    ctx.setSnapshotSectionsVisible(true);
    renderMetrics(snapshot, ctx.elements.metricsGridEl);
    renderDecisionGuidance(snapshot, {
      decisionUpdatedEl: ctx.elements.decisionUpdatedEl,
      decisionBadgeEl: ctx.elements.decisionBadgeEl,
      decisionWindEl: ctx.elements.decisionWindEl,
      decisionQualityEl: ctx.elements.decisionQualityEl,
      decisionRiskEl: ctx.elements.decisionRiskEl,
    });
    renderSummaryTable(snapshot, ctx.elements.summaryOutputEl);
    renderRowsTable(snapshot, ctx.elements.rowsOutputEl);
    const chartState = ctx.charts.renderCore(snapshot);
    ctx.updateChartVisibility(selected?.data ?? [], chartState.hasDirectionData);

    ctx.elements.playbackWindowLabelEl.textContent = `${historyYears}-year loaded history`;
    ctx.timeframeManager.refreshYearOptions(snapshot);

    try {
      await ctx.playbackManager.load(snapshot, ctx.state.baselineStartLocal, ctx.state.baselineEndLocal);
    } catch (error) {
      ctx.setPlaybackSectionVisible(false);
      ctx.setError(error instanceof Error ? error.message : "Unable to prepare playback for this station.");
    }
    try {
      await ctx.timeframeManager.loadAnalytics();
    } catch (error) {
      ctx.setError(error instanceof Error ? error.message : "Unable to run timeframe analysis.");
    }
    ctx.elements.statusEl.textContent = `Analysis ready for ${stationDisplayName(snapshot.selectedStationId, snapshot.selectedStationName)}.`;
    ctx.showToast(`Analysis ready for ${stationDisplayName(snapshot.selectedStationId, snapshot.selectedStationName)}.`);
    ctx.elements.queryProgressWrap.classList.remove("show");
    ctx.setResultsSkeletonVisible(false);
    ctx.setWorkflowStage("explore", "Analysis ready.");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to load station baseline.";
    ctx.setError(message);
    ctx.elements.statusEl.textContent = "Station load failed.";
    ctx.elements.queryProgressWrap.classList.remove("show");
    ctx.setSnapshotSectionsVisible(false);
    ctx.setResultsSkeletonVisible(false);
    ctx.setWorkflowStage("scope", "Review selection and retry.");
  } finally {
    ctx.setLoading(false);
    ctx.setResultsSkeletonVisible(false);
  }
}
