import { fetchJson, formatDateTime, formatNumber } from "../../core/api.js";
import { FeasibilitySnapshotResponse, PlaybackResponse } from "../../core/types.js";
import { clearPlaybackTrail, OverlayController, renderPlaybackOverlay } from "../overlay.js";
import { PlaybackController } from "../playback.js";
import { DashboardCharts } from "./charts.js";
import { setPlaybackButtonVisual, updatePlaybackControls } from "./playback_controls.js";
import { setPlaybackProgress } from "./progress.js";

type PlaybackElements = {
  playbackWindowLabelEl: HTMLParagraphElement;
  playbackProgressBar: HTMLProgressElement;
  playbackProgressText: HTMLParagraphElement;
  playbackProgressWrap: HTMLDivElement;
  playbackPlayBtn: HTMLButtonElement;
  playbackSlider: HTMLInputElement;
  playbackStatusEl: HTMLParagraphElement;
  overlayTempInput: HTMLInputElement;
  overlayPressureInput: HTMLInputElement;
  overlayTrailInput: HTMLInputElement;
  playbackSpeedSelect: HTMLSelectElement;
  playbackLoopInput: HTMLInputElement;
};

type PlaybackManagerDeps = {
  elements: PlaybackElements;
  playbackController: PlaybackController;
  overlayController: OverlayController;
  charts: DashboardCharts;
  ensureAuthenticated: () => boolean;
  setError: (message: string | null) => void;
  setPlaybackSectionVisible: (visible: boolean) => void;
  updateChartVisibility: (
    rows: FeasibilitySnapshotResponse["stations"][number]["data"],
    hasDirectionData: boolean,
  ) => void;
  configuredInputTimeZone: () => string;
  selectedStep: () => string;
  selectedPlaybackDelayMs: () => number;
};

export class PlaybackManager {
  constructor(private readonly deps: PlaybackManagerDeps) {}

  configureEvents(): void {
    this.deps.playbackController.onFrame((frame, index, total) => {
      this.deps.elements.playbackSlider.max = String(Math.max(0, total - 1));
      this.deps.elements.playbackSlider.value = String(index);
      if (!frame) return;
      const frameStatusText = `${formatDateTime(frame.datetime)} · Speed ${formatNumber(frame.speed)} m/s · Direction ${formatNumber(frame.direction)}º · Temp ${formatNumber(frame.temperature)} ºC · Pressure ${formatNumber(frame.pressure)} hPa · ${frame.qualityFlag}`;
      this.deps.elements.playbackStatusEl.textContent = frameStatusText;
      this.deps.elements.playbackStatusEl.title = frameStatusText;
      renderPlaybackOverlay(this.deps.overlayController, frame, {
        showDirectionTrail: this.deps.elements.overlayTrailInput.checked,
        showTemperatureHalo: this.deps.elements.overlayTempInput.checked,
        showPressureRing: this.deps.elements.overlayPressureInput.checked,
      });
    });

    this.deps.elements.playbackPlayBtn.addEventListener("click", () => {
      this.deps.playbackController.toggle();
      setPlaybackButtonVisual(this.deps.elements.playbackPlayBtn, this.deps.playbackController.isPlaying());
    });
    this.deps.elements.playbackSlider.addEventListener("input", () =>
      this.deps.playbackController.setIndex(Number(this.deps.elements.playbackSlider.value))
    );
    this.deps.elements.playbackSpeedSelect.addEventListener("change", () =>
      this.deps.playbackController.setOptions({
        frameDelayMs: this.deps.selectedPlaybackDelayMs(),
        loop: this.deps.elements.playbackLoopInput.checked,
      })
    );
    this.deps.elements.playbackLoopInput.addEventListener("change", () =>
      this.deps.playbackController.setOptions({
        frameDelayMs: this.deps.selectedPlaybackDelayMs(),
        loop: this.deps.elements.playbackLoopInput.checked,
      })
    );
    this.deps.elements.overlayTempInput.addEventListener("change", () =>
      this.deps.playbackController.setIndex(this.deps.playbackController.currentIndex())
    );
    this.deps.elements.overlayPressureInput.addEventListener("change", () =>
      this.deps.playbackController.setIndex(this.deps.playbackController.currentIndex())
    );
    this.deps.elements.overlayTrailInput.addEventListener("change", () =>
      this.deps.playbackController.setIndex(this.deps.playbackController.currentIndex())
    );
  }

  async load(snapshot: FeasibilitySnapshotResponse, baselineStartLocal: string, baselineEndLocal: string): Promise<void> {
    if (!this.deps.ensureAuthenticated()) return;
    if (!baselineStartLocal || !baselineEndLocal) return;
    this.deps.setError(null);
    const params = new URLSearchParams({
      station: snapshot.selectedStationId,
      start: baselineStartLocal,
      end: baselineEndLocal,
      step: this.deps.selectedStep(),
      location: this.deps.configuredInputTimeZone(),
    });
    const payload = await fetchJson<PlaybackResponse>(`/api/analysis/playback?${params.toString()}`);
    const selected = snapshot.stations.find((station) => station.stationId === snapshot.selectedStationId);
    const rows = selected?.data ?? [];
    const hasFrames = payload.frames.length > 0;
    this.deps.setPlaybackSectionVisible(hasFrames);
    if (!hasFrames) {
      this.deps.playbackController.pause();
      setPlaybackButtonVisual(this.deps.elements.playbackPlayBtn, false);
      clearPlaybackTrail(this.deps.overlayController);
      this.deps.elements.playbackWindowLabelEl.textContent = "";
      this.deps.elements.playbackStatusEl.textContent = "Playback frames are not available for this timeframe.";
      this.deps.elements.playbackStatusEl.title = "Playback frames are not available for this timeframe.";
      this.deps.updateChartVisibility(rows, rows.some((row) => row.direction != null));
      return;
    }

    this.deps.elements.playbackWindowLabelEl.textContent = `${formatDateTime(payload.start)} to ${formatDateTime(payload.end)} · ${payload.effectiveStep}`;
    setPlaybackProgress(
      this.deps.elements.playbackProgressWrap,
      this.deps.elements.playbackProgressBar,
      this.deps.elements.playbackProgressText,
      payload.framesReady,
      payload.framesPlanned,
      "Playback ready.",
    );
    updatePlaybackControls(this.deps.elements.playbackSlider, this.deps.elements.playbackPlayBtn, payload.frames.length);
    clearPlaybackTrail(this.deps.overlayController);
    this.deps.playbackController.setFrames(payload.frames);
    this.deps.updateChartVisibility(rows, rows.some((row) => row.direction != null));
    this.deps.charts.renderRose(payload.windRose);
    const concentration =
      payload.windRose.directionalConcentration == null
        ? "n/a"
        : `${(payload.windRose.directionalConcentration * 100).toFixed(1)}%`;
    if (payload.windRose.dominantSector == null) {
      const noDirectionText =
        "Direction values are not available for this timeframe. Speed, temperature, and pressure remain available.";
      this.deps.elements.playbackStatusEl.textContent = noDirectionText;
      this.deps.elements.playbackStatusEl.title = noDirectionText;
      return;
    }
    const playbackSummaryText =
      `Dominant direction: ${payload.windRose.dominantSector} · Concentration: ${concentration} · Calm share: ${
        payload.windRose.calmShare == null ? "n/a" : `${(payload.windRose.calmShare * 100).toFixed(1)}%`
      }`;
    this.deps.elements.playbackStatusEl.textContent = playbackSummaryText;
    this.deps.elements.playbackStatusEl.title = playbackSummaryText;
  }
}
