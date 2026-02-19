declare const Chart: any;

import { TimeframeAnalyticsResponse } from "../../core/types.js";
import { computeNumericStats } from "./chart_data.js";
import { datasetValueAt, formatTooltipBucketTitle, formatTooltipValue } from "./chart_tooltips.js";

export function renderTimeframeTrendChart(payload: TimeframeAnalyticsResponse, canvas: HTMLCanvasElement): any {
  if (!payload.buckets.length) return null;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const labels = payload.buckets.map((bucket) => bucket.label);
  const minSpeedSeries = payload.buckets.map((bucket) => bucket.minSpeed);
  const avgSpeedSeries = payload.buckets.map((bucket) => bucket.avgSpeed);
  const maxSpeedSeries = payload.buckets.map((bucket) => bucket.maxSpeed);
  const p90Series = payload.buckets.map((bucket) => bucket.p90Speed);
  const avgTempSeries = payload.buckets.map((bucket) => bucket.avgTemperature);
  const minTempSeries = payload.buckets.map((bucket) => bucket.minTemperature);
  const maxTempSeries = payload.buckets.map((bucket) => bucket.maxTemperature);
  const generationSeries = payload.buckets.map((bucket) => bucket.estimatedGenerationMwh);

  const speedStats = computeNumericStats(avgSpeedSeries);
  const generationStats = computeNumericStats(generationSeries);

  const datasets: any[] = [
    {
      type: "line",
      label: "__speed_floor",
      data: minSpeedSeries,
      borderColor: "rgba(15, 23, 42, 0)",
      borderWidth: 0.8,
      pointRadius: 0,
      tension: 0.18,
      yAxisID: "ySpeed",
      spanGaps: true,
    },
    {
      type: "line",
      label: "Speed range (min-max)",
      data: maxSpeedSeries,
      borderColor: "rgba(14, 165, 233, 0.45)",
      backgroundColor: "rgba(14, 165, 233, 0.18)",
      borderWidth: 1.3,
      pointRadius: 0,
      fill: "-1",
      tension: 0.2,
      yAxisID: "ySpeed",
      spanGaps: true,
    },
    {
      type: "line",
      label: "Avg speed",
      data: avgSpeedSeries,
      borderColor: "#0f766e",
      borderWidth: 2.2,
      pointRadius: 1.5,
      pointHoverRadius: 3,
      tension: 0.24,
      yAxisID: "ySpeed",
      spanGaps: true,
    },
    {
      type: "line",
      label: "P90 speed",
      data: p90Series,
      borderColor: "#0ea5e9",
      borderWidth: 1.6,
      borderDash: [5, 4],
      pointRadius: 0,
      tension: 0.2,
      yAxisID: "ySpeed",
      spanGaps: true,
    },
    {
      type: "line",
      label: "__temp_floor",
      data: minTempSeries,
      borderColor: "rgba(59, 130, 246, 0)",
      borderWidth: 0.8,
      pointRadius: 0,
      tension: 0.16,
      yAxisID: "yTemp",
      spanGaps: true,
    },
    {
      type: "line",
      label: "Temp range (min-max)",
      data: maxTempSeries,
      borderColor: "rgba(239, 68, 68, 0.56)",
      backgroundColor: "rgba(248, 113, 113, 0.12)",
      borderWidth: 1.2,
      pointRadius: 0,
      fill: "-1",
      tension: 0.16,
      yAxisID: "yTemp",
      spanGaps: true,
    },
    {
      type: "line",
      label: "Avg temp",
      data: avgTempSeries,
      borderColor: "rgba(185, 28, 28, 0.92)",
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      tension: 0.16,
      yAxisID: "yTemp",
      spanGaps: true,
    },
  ];

  if (generationStats) {
    datasets.push({
      type: "bar",
      label: "Generation (MWh)",
      data: generationSeries,
      yAxisID: "yGeneration",
      backgroundColor: "rgba(14, 165, 233, 0.25)",
      borderColor: "rgba(14, 165, 233, 0.8)",
      borderWidth: 1,
      borderRadius: 4,
      barThickness: 14,
    });
  }

  return new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: {
            usePointStyle: true,
            boxWidth: 8,
            font: { size: 11 },
            filter: (item: { text?: string }) => !(item.text ?? "").startsWith("__"),
          },
        },
        tooltip: {
          filter: (context: { dataset?: { label?: string } }) => !((context.dataset?.label ?? "").startsWith("__")),
          callbacks: {
            title: (items: Array<{ dataIndex?: number }>) => {
              const dataIndex = items[0]?.dataIndex ?? -1;
              const bucket = payload.buckets[dataIndex];
              if (!bucket) return "";
              return formatTooltipBucketTitle(bucket.label, bucket.start, bucket.end);
            },
            label: (context: {
              chart: any;
              datasetIndex: number;
              dataIndex: number;
              dataset?: { label?: string };
              parsed?: { y?: number };
            }) => {
              const label = context.dataset?.label ?? "";
              if (label === "Speed range (min-max)") {
                const minSpeed = datasetValueAt(context.chart, context.datasetIndex - 1, context.dataIndex);
                return `Wind min-max: ${formatTooltipValue(minSpeed)} to ${formatTooltipValue(context.parsed?.y)} m/s`;
              }
              if (label === "Avg speed") {
                return `Wind avg: ${formatTooltipValue(context.parsed?.y)} m/s`;
              }
              if (label === "P90 speed") {
                return `Wind P90: ${formatTooltipValue(context.parsed?.y)} m/s`;
              }
              if (label === "Temp range (min-max)") {
                const minTemp = datasetValueAt(context.chart, context.datasetIndex - 1, context.dataIndex);
                return `Temp min-max: ${formatTooltipValue(minTemp)} to ${formatTooltipValue(context.parsed?.y)} C`;
              }
              if (label === "Avg temp") {
                return `Temp avg: ${formatTooltipValue(context.parsed?.y)} C`;
              }
              if (label === "Generation (MWh)") {
                return `Generation: ${formatTooltipValue(context.parsed?.y, 3)} MWh`;
              }
              return `${label}: ${formatTooltipValue(context.parsed?.y)}`;
            },
          },
          padding: 8,
          boxPadding: 2,
          bodySpacing: 3,
        },
        subtitle: speedStats
          ? {
              display: true,
              text: `Avg-speed min/avg/max ${speedStats.min.toFixed(2)} / ${speedStats.avg.toFixed(2)} / ${speedStats.max.toFixed(2)} m/s`,
              color: "#475569",
              padding: { bottom: 8 },
              font: { size: 11, weight: "600" },
            }
          : { display: false },
      },
      scales: {
        x: {
          grid: { color: "rgba(148, 163, 184, 0.16)" },
          ticks: {
            color: "#475569",
            maxRotation: labels.length > 10 ? 32 : 0,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 14,
            padding: 5,
          },
        },
        ySpeed: {
          type: "linear",
          position: "left",
          grid: { color: "rgba(148, 163, 184, 0.24)" },
          title: { display: true, text: "Wind speed (m/s)", color: "#0f766e", font: { size: 11, weight: "700" } },
          ticks: { callback: (value: number) => `${value}` },
        },
        yTemp: {
          type: "linear",
          position: "right",
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Temperature (ºC)", color: "#b91c1c", font: { size: 11, weight: "700" } },
          ticks: { callback: (value: number) => `${value}` },
        },
        yGeneration: {
          type: "linear",
          position: "right",
          display: Boolean(generationStats),
          grid: { drawOnChartArea: false },
          title: { display: Boolean(generationStats), text: "Generation (MWh)", color: "#0369a1", font: { size: 11, weight: "700" } },
          ticks: { callback: (value: number) => `${value}` },
        },
      },
    },
  });
}
