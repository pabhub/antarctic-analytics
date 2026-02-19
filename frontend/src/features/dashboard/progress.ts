import { QueryJobCreateResponse, QueryJobStatusResponse } from "../../core/types.js";

function normalizeMessage(message: string): string {
  const normalized = message
    .replace(/\bwindow\b/gi, "month")
    .replace(/\bwindows\b/gi, "months");
  if (/^Fetching month\s+\d+\/\d+/i.test(normalized)) {
    return "Fetching missing months.";
  }
  return normalized;
}

export function setQueryProgress(
  queryProgressWrap: HTMLDivElement,
  queryProgressBar: HTMLProgressElement,
  queryProgressText: HTMLParagraphElement,
  status: QueryJobCreateResponse | QueryJobStatusResponse,
): void {
  queryProgressWrap.classList.add("show");
  const completedMonths = "completedWindows" in status ? status.completedWindows : status.cachedWindows;
  queryProgressBar.max = Math.max(1, status.totalWindows);
  queryProgressBar.value = Math.min(status.totalWindows, completedMonths);
  const monthLabel = status.totalWindows === 1 ? "month" : "months";
  queryProgressText.textContent =
    `${normalizeMessage(status.message)} Loaded ${completedMonths}/${status.totalWindows} ${monthLabel} (${status.cachedWindows} cached).`;
}

export function setQueryProgressAnalyzing(
  queryProgressWrap: HTMLDivElement,
  queryProgressBar: HTMLProgressElement,
  queryProgressText: HTMLParagraphElement,
  totalMonths: number,
  message: string,
): void {
  queryProgressWrap.classList.add("show");
  queryProgressBar.max = Math.max(1, totalMonths);
  queryProgressBar.value = Math.max(1, totalMonths);
  queryProgressText.textContent = message;
}

export function setPlaybackProgress(
  playbackProgressWrap: HTMLDivElement,
  playbackProgressBar: HTMLProgressElement,
  playbackProgressText: HTMLParagraphElement,
  ready: number,
  total: number,
  message: string,
): void {
  playbackProgressWrap.classList.add("show");
  playbackProgressBar.max = Math.max(1, total);
  playbackProgressBar.value = Math.min(ready, total);
  playbackProgressText.textContent = `${message} Frames ${ready}/${total}.`;
}
