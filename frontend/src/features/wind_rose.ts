declare const Chart: any;

import { WindRoseSummary } from "../core/types.js";

const SECTOR_ORDER = [
  "N", "NNE", "NE", "ENE",
  "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW",
  "W", "WNW", "NW", "NNW",
];

const BUCKETS: Array<{ key: string; label: string; color: string; fill: string }> = [
  { key: "calm", label: "< 3 m/s", color: "#38bdf8", fill: "rgba(56, 189, 248, 0.32)" },
  { key: "breeze", label: "3-8 m/s", color: "#22c55e", fill: "rgba(34, 197, 94, 0.3)" },
  { key: "strong", label: "8-12 m/s", color: "#f59e0b", fill: "rgba(245, 158, 11, 0.28)" },
  { key: "gale", label: ">= 12 m/s", color: "#ef4444", fill: "rgba(239, 68, 68, 0.26)" },
];

function valueFor(bin: { speedBuckets: Record<string, number> }, bucketKey: string): number {
  return Math.max(0, Number(bin.speedBuckets[bucketKey] ?? 0));
}

function totalSamples(rose: WindRoseSummary): number {
  return rose.bins.reduce((sum, bin) => sum + Math.max(0, bin.totalCount ?? 0), 0);
}

const compassBackdropPlugin = {
  id: "compassBackdrop",
  beforeDatasetsDraw(chart: any) {
    const radial = chart?.scales?.r;
    if (!radial) return;
    const ctx = chart.ctx;
    const centerX = radial.xCenter;
    const centerY = radial.yCenter;
    const radius = radial.drawingArea;

    const gradient = ctx.createRadialGradient(centerX, centerY, radius * 0.1, centerX, centerY, radius);
    gradient.addColorStop(0, "rgba(14, 165, 233, 0.12)");
    gradient.addColorStop(1, "rgba(15, 23, 42, 0)");

    ctx.save();
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.restore();
  },
};

const cardinalCrossPlugin = {
  id: "cardinalCross",
  afterDraw(chart: any) {
    const radial = chart?.scales?.r;
    if (!radial) return;

    const ctx = chart.ctx;
    const centerX = radial.xCenter;
    const centerY = radial.yCenter;
    const radius = radial.drawingArea;

    ctx.save();
    ctx.strokeStyle = "rgba(15, 23, 42, 0.58)";
    ctx.lineWidth = 1.3;

    ctx.beginPath();
    ctx.moveTo(centerX, centerY - radius);
    ctx.lineTo(centerX, centerY + radius);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(centerX - radius, centerY);
    ctx.lineTo(centerX + radius, centerY);
    ctx.stroke();
    ctx.restore();
  },
};

export function renderWindRoseChart(canvas: HTMLCanvasElement, rose: WindRoseSummary): any {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const binBySector = new Map(rose.bins.map((bin) => [bin.sector, bin]));
  const orderedBins = SECTOR_ORDER.map((sector) => {
    const fallback = {
      sector,
      speedBuckets: { calm: 0, breeze: 0, strong: 0, gale: 0 },
      totalCount: 0,
    };
    return binBySector.get(sector) ?? fallback;
  });

  const total = Math.max(1, totalSamples(rose));
  const cumulativeByBucket = BUCKETS.map(() => Array.from({ length: orderedBins.length }, () => 0));
  for (let index = 0; index < orderedBins.length; index += 1) {
    let cumulative = 0;
    BUCKETS.forEach((bucket, bucketIndex) => {
      cumulative += valueFor(orderedBins[index], bucket.key);
      cumulativeByBucket[bucketIndex][index] = Number(((cumulative / total) * 100).toFixed(3));
    });
  }

  const maxPct = Math.max(5, ...cumulativeByBucket[cumulativeByBucket.length - 1]);
  const tickStep = maxPct > 40 ? 10 : maxPct > 20 ? 5 : 2;

  return new Chart(ctx, {
    type: "radar",
    data: {
      labels: SECTOR_ORDER,
      datasets: BUCKETS.map((bucket, index) => ({
        label: bucket.label,
        data: cumulativeByBucket[index],
        borderColor: bucket.color,
        backgroundColor: bucket.fill,
        borderWidth: index === BUCKETS.length - 1 ? 2.2 : 1.8,
        pointRadius: 0.8,
        pointHoverRadius: 2.2,
        fill: index === 0 ? true : "-1",
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: {
        line: { tension: 0.08 },
      },
      scales: {
        r: {
          beginAtZero: true,
          suggestedMax: Math.ceil(maxPct / tickStep) * tickStep,
          angleLines: { color: "rgba(148, 163, 184, 0.3)" },
          grid: { color: "rgba(148, 163, 184, 0.28)" },
          ticks: {
            stepSize: tickStep,
            showLabelBackdrop: false,
            color: "#475569",
            callback: (value: number) => `${value}%`,
            font: { size: 10, weight: "600" },
          },
          pointLabels: {
            color: "#334155",
            font: { size: 10, weight: "700" },
          },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } },
        },
        subtitle: {
          display: true,
          text:
            rose.dominantSector == null
              ? "No directional distribution available for this timeframe."
              : `Dominant heading (toward): ${rose.dominantSector} · Directional concentration ${((rose.directionalConcentration ?? 0) * 100).toFixed(1)}% · Calm share ${((rose.calmShare ?? 0) * 100).toFixed(1)}%`,
          color: "#475569",
          padding: { bottom: 8 },
          font: { size: 11, weight: "600" },
        },
        tooltip: {
          callbacks: {
            title: (context: any[]) => {
              const sector = context?.[0]?.label;
              return sector ? `Sector ${sector}` : "";
            },
            label: (context: any) => {
              const datasetLabel = context.dataset?.label ?? "";
              const value = Number(context.raw ?? 0);
              return `${datasetLabel}: ${value.toFixed(2)}% cumulative`;
            },
          },
        },
      },
    },
    plugins: [compassBackdropPlugin, cardinalCrossPlugin],
  });
}
