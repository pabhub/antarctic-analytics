import { QueryJobCreateResponse, QueryJobStatusResponse } from "../../core/types.js";
import { OverlayController } from "../overlay.js";
import { PlaybackController } from "../playback.js";
import { DashboardCharts } from "./charts.js";
import { DashboardState } from "./dashboard_state.js";
import { PlaybackManager } from "./playback_manager.js";
import { TimeframeManager } from "./timeframe_manager.js";

export type WorkflowStage = "auth" | "scope" | "fetch" | "explore";
export type MeasurementRow = NonNullable<DashboardState["snapshotState"]>["stations"][number]["data"][number];

export type LatestAvailabilityPayload = {
  station: string;
  checked_at_utc: string;
  newest_observation_utc: string | null;
  suggested_start_utc: string | null;
  suggested_end_utc: string | null;
  probe_window_hours: number | null;
  suggested_aggregation: string | null;
  note: string;
};

export type DashboardActionElements = {
  stationSelect: HTMLSelectElement;
  statusEl: HTMLParagraphElement;
  playbackProgressWrap: HTMLDivElement;
  queryProgressWrap: HTMLDivElement;
  queryProgressBar: HTMLProgressElement;
  queryProgressText: HTMLParagraphElement;
  playbackWindowLabelEl: HTMLParagraphElement;
  timeframeCardsEl: HTMLDivElement;
  timeframeBodyEl: HTMLTableSectionElement;
  timeframeComparisonEl: HTMLDivElement;
  timeframeGenerationEl: HTMLParagraphElement;
  metricsGridEl: HTMLDivElement;
  summaryOutputEl: HTMLTableSectionElement;
  rowsOutputEl: HTMLTableSectionElement;
  decisionUpdatedEl: HTMLParagraphElement;
  decisionBadgeEl: HTMLSpanElement;
  decisionWindEl: HTMLParagraphElement;
  decisionQualityEl: HTMLParagraphElement;
  decisionRiskEl: HTMLParagraphElement;
};

export type DashboardActionsContext = {
  state: DashboardState;
  map: any;
  overlayController: OverlayController;
  playbackController: PlaybackController;
  charts: DashboardCharts;
  playbackManager: PlaybackManager;
  timeframeManager: TimeframeManager;
  elements: DashboardActionElements;
  configuredInputTimeZone: () => string;
  selectedStep: () => string;
  selectedHistoryYears: () => number;
  ensureAuthenticated: () => boolean;
  getMapStationClickHandler: () => (stationId: string) => void;
  setWorkflowStage: (stage: WorkflowStage, helperText?: string) => void;
  setPlaybackSectionVisible: (visible: boolean) => void;
  setTimeframeSectionVisible: (visible: boolean) => void;
  setSnapshotSectionsVisible: (visible: boolean) => void;
  setResultsSkeletonVisible: (visible: boolean) => void;
  updateChartVisibility: (rows: MeasurementRow[], hasDirectionData: boolean) => void;
  setError: (message: string | null) => void;
  setLoading: (loading: boolean) => void;
  setPlaybackButtonVisual: (playing: boolean) => void;
  setQueryProgress: (status: QueryJobCreateResponse | QueryJobStatusResponse) => void;
  setQueryProgressAnalyzing: (totalMonths: number, message: string) => void;
  showToast: (message: string) => void;
};
