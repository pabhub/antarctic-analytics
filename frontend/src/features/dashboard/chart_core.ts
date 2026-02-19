declare const Chart: any;

import { FeasibilitySnapshotResponse } from "../../core/types.js";
import { aggregateRowsToEnvelopes, envelopeSummary, granularityLabel, timeAxisConfig, timeSpanDays } from "./chart_data.js";
import { datasetValueAt, formatTooltipDateTime, formatTooltipValue } from "./chart_tooltips.js";

export type CoreChartRenderResult = {
  windChart: any;
  weatherChart: any;
  hasSpeedData: boolean;
  hasWeatherData: boolean;
  hasDirectionData: boolean;
};

export function renderCoreCharts(
  snapshot: FeasibilitySnapshotResponse,
  windChartCanvas: HTMLCanvasElement,
  weatherChartCanvas: HTMLCanvasElement,
): CoreChartRenderResult {
  const selected = snapshot.stations.find((station) => station.stationId === snapshot.selectedStationId);
  const rows = selected?.data ?? [];
  const aggregated = aggregateRowsToEnvelopes(rows);
  const labels = aggregated.labels;
  const spanDays = timeSpanDays(labels);
  const granularityText = granularityLabel(aggregated.granularity);
  const chartTimeZone = snapshot.timezone_output || snapshot.timezone_input || "UTC";
  const hasSpeedData = rows.some((row) => row.speed != null);
  const hasWeatherData = rows.some((row) => row.temperature != null || row.pressure != null);
  const hasDirectionData = rows.some((row) => row.direction != null);

  let windChart: any = null;
  let weatherChart: any = null;

  const windCtx = windChartCanvas.getContext("2d");
  if (hasSpeedData && windCtx) {
    const speedStats = envelopeSummary(aggregated.speed);
    const windDatasets: any[] = [
      {
        label: "__speed_floor",
        data: aggregated.speed.min,
        borderColor: "rgba(15, 23, 42, 0)",
        backgroundColor: "rgba(15, 23, 42, 0)",
        borderWidth: 0.8,
        spanGaps: true,
        pointRadius: 0,
        fill: false,
      },
      {
        label: "Speed range (min-max)",
        data: aggregated.speed.max,
        borderColor: "rgba(14, 165, 233, 0.45)",
        backgroundColor: "rgba(14, 165, 233, 0.18)",
        borderWidth: 1.4,
        spanGaps: true,
        pointRadius: 0,
        fill: "-1",
        tension: 0.2,
      },
      {
        label: "Avg speed",
        data: aggregated.speed.avg,
        borderColor: "#0f766e",
        borderWidth: 2.2,
        pointRadius: 0,
        fill: false,
        tension: 0.22,
        spanGaps: true,
      },
    ];
    windChart = new Chart(windCtx, {
      type: "line",
      data: {
        labels,
        datasets: windDatasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          decimation: { enabled: labels.length > 300, algorithm: "lttb", samples: 220 },
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
              title: (items: Array<{ label?: string }>) => formatTooltipDateTime(items[0]?.label ?? ""),
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
                text: `${granularityText} min/avg/max ${speedStats.min.toFixed(2)} / ${speedStats.avg.toFixed(2)} / ${speedStats.max.toFixed(2)} m/s`,
                color: "#475569",
                padding: { bottom: 8 },
                font: { size: 11, weight: "600" },
              }
            : { display: false },
        },
        scales: {
          x: timeAxisConfig(labels, spanDays, chartTimeZone),
          y: {
            grid: { color: "rgba(148, 163, 184, 0.22)" },
            ticks: { callback: (value: number) => `${value} m/s` },
            title: { display: true, text: "Wind speed (m/s)", color: "#334155", font: { size: 11, weight: "700" } },
          },
        },
      },
    });
  }

  const weatherCtx = weatherChartCanvas.getContext("2d");
  if (hasWeatherData && weatherCtx) {
    const temperatureStats = envelopeSummary(aggregated.temperature);
    const pressureStats = envelopeSummary(aggregated.pressure);
    const weatherDatasets: any[] = [
      {
        label: "__temp_floor",
        data: aggregated.temperature.min,
        borderColor: "rgba(220, 38, 38, 0)",
        yAxisID: "yTemp",
        borderWidth: 0.8,
        pointRadius: 0,
        spanGaps: true,
        fill: false,
      },
      {
        label: "Temp range (min-max)",
        data: aggregated.temperature.max,
        borderColor: "rgba(220, 38, 38, 0.5)",
        backgroundColor: "rgba(248, 113, 113, 0.14)",
        yAxisID: "yTemp",
        borderWidth: 1.2,
        fill: "-1",
        pointRadius: 0,
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "Avg temp",
        data: aggregated.temperature.avg,
        borderColor: "#dc2626",
        yAxisID: "yTemp",
        borderWidth: 2.1,
        pointRadius: 0,
        tension: 0.22,
        spanGaps: true,
      },
      {
        label: "__press_floor",
        data: aggregated.pressure.min,
        borderColor: "rgba(2, 132, 199, 0)",
        yAxisID: "yPress",
        borderWidth: 0.8,
        pointRadius: 0,
        fill: false,
        spanGaps: true,
      },
      {
        label: "Pressure range (min-max)",
        data: aggregated.pressure.max,
        borderColor: "rgba(2, 132, 199, 0.55)",
        backgroundColor: "rgba(56, 189, 248, 0.14)",
        yAxisID: "yPress",
        borderWidth: 1.2,
        pointRadius: 0,
        fill: "-1",
        spanGaps: true,
        tension: 0.2,
      },
      {
        label: "Avg pressure",
        data: aggregated.pressure.avg,
        borderColor: "#0284c7",
        yAxisID: "yPress",
        borderWidth: 2.1,
        pointRadius: 0,
        tension: 0.22,
        spanGaps: true,
      },
    ];
    const subtitleParts: string[] = [];
    if (temperatureStats) {
      subtitleParts.push(
        `Temp min/avg/max ${temperatureStats.min.toFixed(1)} / ${temperatureStats.avg.toFixed(1)} / ${temperatureStats.max.toFixed(1)} ºC`,
      );
    }
    if (pressureStats) {
      subtitleParts.push(
        `Pressure min/avg/max ${pressureStats.min.toFixed(1)} / ${pressureStats.avg.toFixed(1)} / ${pressureStats.max.toFixed(1)} hPa`,
      );
    }
    weatherChart = new Chart(weatherCtx, {
      type: "line",
      data: {
        labels,
        datasets: weatherDatasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          decimation: { enabled: labels.length > 300, algorithm: "lttb", samples: 220 },
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
              title: (items: Array<{ label?: string }>) => formatTooltipDateTime(items[0]?.label ?? ""),
              label: (context: {
                chart: any;
                datasetIndex: number;
                dataIndex: number;
                dataset?: { label?: string };
                parsed?: { y?: number };
              }) => {
                const label = context.dataset?.label ?? "";
                if (label === "Temp range (min-max)") {
                  const minTemp = datasetValueAt(context.chart, context.datasetIndex - 1, context.dataIndex);
                  return `Temp min-max: ${formatTooltipValue(minTemp)} to ${formatTooltipValue(context.parsed?.y)} C`;
                }
                if (label === "Avg temp") {
                  return `Temp avg: ${formatTooltipValue(context.parsed?.y)} C`;
                }
                if (label === "Pressure range (min-max)") {
                  const minPressure = datasetValueAt(context.chart, context.datasetIndex - 1, context.dataIndex);
                  return `Pressure min-max: ${formatTooltipValue(minPressure, 1)} to ${formatTooltipValue(context.parsed?.y, 1)} hPa`;
                }
                if (label === "Avg pressure") {
                  return `Pressure avg: ${formatTooltipValue(context.parsed?.y, 1)} hPa`;
                }
                return `${label}: ${formatTooltipValue(context.parsed?.y)}`;
              },
            },
            padding: 8,
            boxPadding: 2,
            bodySpacing: 3,
          },
          subtitle: subtitleParts.length
            ? {
                display: true,
                text: `${granularityText} intervals · ${subtitleParts.join(" · ")}`,
                color: "#475569",
                padding: { bottom: 8 },
                font: { size: 11, weight: "600" },
              }
            : { display: false },
        },
        scales: {
          x: timeAxisConfig(labels, spanDays, chartTimeZone),
          yTemp: {
            type: "linear",
            position: "left",
            grid: { color: "rgba(248, 113, 113, 0.18)" },
            ticks: { callback: (value: number) => `${value} ºC` },
            title: { display: true, text: "Temperature (ºC)", color: "#991b1b", font: { size: 11, weight: "700" } },
          },
          yPress: {
            type: "linear",
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: { callback: (value: number) => `${value} hPa` },
            title: { display: true, text: "Pressure (hPa)", color: "#0369a1", font: { size: 11, weight: "700" } },
          },
        },
      },
    });
  }

  return { windChart, weatherChart, hasSpeedData, hasWeatherData, hasDirectionData };
}
