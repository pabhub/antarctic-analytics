declare const L: any;
declare const Chart: any;

type DataRow = {
  stationName: string;
  datetime: string;
  temperature?: number | null;
  pressure?: number | null;
  speed?: number | null;
  direction?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  altitude?: number | null;
};

const form = document.getElementById('query-form') as HTMLFormElement;
const output = document.getElementById('output') as HTMLTableSectionElement;
const statusEl = document.getElementById('status') as HTMLParagraphElement;
const chips = document.getElementById('summary-chips') as HTMLDivElement;
const avgOutput = document.getElementById('avg-output') as HTMLTableSectionElement;
const timeline = document.getElementById('timeline') as HTMLInputElement;
const timelineLabel = document.getElementById('timeline-label') as HTMLSpanElement;
const playButton = document.getElementById('play-timeline') as HTMLButtonElement;
const speedChartCanvas = document.getElementById('speed-chart') as HTMLCanvasElement;
const weatherChartCanvas = document.getElementById('weather-chart') as HTMLCanvasElement;
const startInput = document.getElementById('start') as HTMLInputElement;
const endInput = document.getElementById('end') as HTMLInputElement;
const locationSelect = document.getElementById('location') as HTMLSelectElement;
const displayTimezoneSelect = document.getElementById('display-timezone') as HTMLSelectElement;
const rangeButtons = Array.from(document.querySelectorAll('.range-btn')) as HTMLButtonElement[];
const loadingOverlay = document.getElementById('loading-overlay') as HTMLDivElement;
const submitBtn = document.getElementById('submit-btn') as HTMLButtonElement;
const metricRows = document.getElementById('metric-rows') as HTMLParagraphElement;
const metricSpeed = document.getElementById('metric-speed') as HTMLParagraphElement;
const metricPeak = document.getElementById('metric-peak') as HTMLParagraphElement;
const metricTemp = document.getElementById('metric-temp') as HTMLParagraphElement;
const exportCsvBtn = document.getElementById('export-csv') as HTMLButtonElement;
const exportParquetBtn = document.getElementById('export-parquet') as HTMLButtonElement;
const emptyState = document.getElementById('empty-state') as HTMLDivElement;
const chartEmpty = document.getElementById('chart-empty') as HTMLDivElement;
const chartsGrid = document.getElementById('charts-grid') as HTMLDivElement;

const map = L.map('map-canvas', { zoomControl: true }).setView([-62.0, -58.5], 4);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const flowLayer = L.layerGroup().addTo(map);

let timelineFrames: string[] = [];
let rowsByTimestamp = new Map<string, DataRow[]>();
let playingTimer: number | null = null;
let speedChart: any = null;
let weatherChart: any = null;
let activeRows: DataRow[] = [];
let lastQueryBasePath = '';
let lastQueryParams = '';

function setLoading(loading: boolean): void {
  loadingOverlay.classList.toggle('hidden', !loading);
  submitBtn.disabled = loading;
  exportCsvBtn.disabled = loading || activeRows.length === 0;
  exportParquetBtn.disabled = loading || activeRows.length === 0;
  submitBtn.textContent = loading ? 'Running query…' : 'Run query';
}

function toDateTimeLocal(date: Date): string {
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function setDefaultRange(): void {
  const end = new Date();
  const start = new Date(end.getTime() - 6 * 60 * 60 * 1000);
  startInput.value = toDateTimeLocal(start);
  endInput.value = toDateTimeLocal(end);
}

function applyQuickRange(range: string): void {
  const end = new Date();
  const amount = range === '6h' ? 6 : range === '24h' ? 24 : 24 * 7;
  const start = new Date(end.getTime() - amount * 60 * 60 * 1000);
  startInput.value = toDateTimeLocal(start);
  endInput.value = toDateTimeLocal(end);
}

function toApiDateTime(value: string): string {
  if (!value) return '';
  return value.length === 16 ? `${value}:00` : value;
}

function selectedTypes(): string[] {
  const checkboxes = Array.from(document.querySelectorAll('input[name="types"]')) as HTMLInputElement[];
  return checkboxes.filter((box) => box.checked).map((box) => box.value);
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? 'n/a' : value.toFixed(digits);
}

function uiTimeZone(): string {
  return displayTimezoneSelect.value === 'browser' ? Intl.DateTimeFormat().resolvedOptions().timeZone : displayTimezoneSelect.value;
}

function formatDateTime(iso: string): string {
  const dt = new Date(iso);
  return new Intl.DateTimeFormat(undefined, {
    timeZone: uiTimeZone(),
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(dt);
}

function setEmptyState(show: boolean, message: string): void {
  emptyState.textContent = message;
  emptyState.classList.toggle('hidden', !show);
}

function renderEmptyRow(target: HTMLTableSectionElement, colspan: number, message: string): void {
  target.innerHTML = '';
  const tr = document.createElement('tr');
  tr.innerHTML = `<td colspan="${colspan}">${message}</td>`;
  target.appendChild(tr);
}

function renderSummary(totalRows: number, mappedRows: number): void {
  chips.innerHTML = '';
  const items = [
    `Rows: ${totalRows}`,
    `Mapped points: ${mappedRows}`,
    `Unmapped rows: ${Math.max(0, totalRows - mappedRows)}`,
    `Display TZ: ${uiTimeZone()}`,
  ];

  for (const item of items) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = item;
    chips.appendChild(chip);
  }
}

function exportUrl(format: 'csv' | 'parquet'): string {
  if (!lastQueryBasePath) return '';
  return `/api/antartida/export/${lastQueryBasePath}?${lastQueryParams}&format=${format}`;
}

async function downloadExport(format: 'csv' | 'parquet'): Promise<void> {
  if (!lastQueryBasePath) {
    statusEl.textContent = 'Run a query before exporting.';
    return;
  }

  const response = await fetch(exportUrl(format));
  if (!response.ok) {
    const details = await response.json().catch(() => ({}));
    statusEl.textContent = details.detail ?? `Failed to export ${format.toUpperCase()}.`;
    return;
  }

  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match?.[1] ?? `aemet_export.${format}`;

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderMetrics(data: DataRow[]): void {
  const speeds = data.map((r) => r.speed).filter((v): v is number => v != null);
  const temps = data.map((r) => r.temperature).filter((v): v is number => v != null);
  metricRows.textContent = String(data.length);
  metricSpeed.textContent = speeds.length ? `${formatNumber(speeds.reduce((a, b) => a + b, 0) / speeds.length)} m/s` : 'n/a';
  metricPeak.textContent = speeds.length ? `${formatNumber(Math.max(...speeds))} m/s` : 'n/a';
  metricTemp.textContent = temps.length ? `${formatNumber(temps.reduce((a, b) => a + b, 0) / temps.length)} °C` : 'n/a';
}

function degToFlowVector(directionDeg: number, length: number): { dx: number; dy: number } {
  const toDeg = (directionDeg + 180) % 360;
  const rad = (toDeg * Math.PI) / 180;
  return { dx: length * Math.sin(rad), dy: length * Math.cos(rad) };
}

function drawFrame(timestamp: string): void {
  markerLayer.clearLayers();
  flowLayer.clearLayers();

  const frameRows = rowsByTimestamp.get(timestamp) ?? [];
  timelineLabel.textContent = formatDateTime(timestamp);

  const bounds: Array<[number, number]> = [];
  for (const row of frameRows) {
    if (row.latitude == null || row.longitude == null) continue;

    const lat = Number(row.latitude);
    const lon = Number(row.longitude);
    const speed = row.speed == null ? null : Number(row.speed);
    const direction = row.direction == null ? null : Number(row.direction);

    const marker = L.circleMarker([lat, lon], {
      radius: 7,
      color: '#0f766e',
      fillColor: '#14b8a6',
      fillOpacity: 0.9,
      weight: 2,
    });
    marker.bindPopup(`<strong>${row.stationName}</strong><br/>Time: ${formatDateTime(row.datetime)}<br/>Speed: ${formatNumber(speed)} m/s<br/>Direction: ${formatNumber(direction)}°`);
    marker.addTo(markerLayer);

    if (speed != null && direction != null) {
      const vectorLength = Math.min(0.2, Math.max(0.03, speed * 0.01));
      const vector = degToFlowVector(direction, vectorLength);
      const endLat = lat + vector.dy;
      const endLon = lon + vector.dx;

      L.polyline([[lat, lon], [endLat, endLon]], { color: '#f97316', weight: 3, opacity: 0.9 }).addTo(flowLayer);
      L.circleMarker([endLat, endLon], { radius: 3, color: '#f97316', fillColor: '#fb923c', fillOpacity: 1, weight: 1 }).addTo(flowLayer);
    }

    bounds.push([lat, lon]);
  }

  if (bounds.length > 0) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 8 });
}

function renderAverages(data: DataRow[]): void {
  avgOutput.innerHTML = '';
  if (data.length === 0) {
    renderEmptyRow(avgOutput, 4, 'No rows to aggregate in this window.');
    return;
  }
  const grouped = new Map<string, DataRow[]>();

  for (const row of data) {
    const bucket = grouped.get(row.stationName) ?? [];
    bucket.push(row);
    grouped.set(row.stationName, bucket);
  }

  for (const [station, rows] of grouped.entries()) {
    const speeds = rows.map((r) => r.speed).filter((x): x is number => x != null);
    const directions = rows.map((r) => r.direction).filter((x): x is number => x != null);

    const avgSpeed = speeds.length ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null;

    let avgDirection: number | null = null;
    if (directions.length) {
      const x = directions.reduce((sum, d) => sum + Math.cos((d * Math.PI) / 180), 0);
      const y = directions.reduce((sum, d) => sum + Math.sin((d * Math.PI) / 180), 0);
      avgDirection = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${station}</td><td>${formatNumber(avgSpeed)}</td><td>${formatNumber(avgDirection)}</td><td>${rows.length}</td>`;
    avgOutput.appendChild(tr);
  }
}


function formatChartAxisLabel(iso: string): string {
  const dt = new Date(iso);
  const sameDay = activeRows.length > 0 && new Date(activeRows[0].datetime).toDateString() === dt.toDateString();
  return new Intl.DateTimeFormat(undefined, {
    timeZone: uiTimeZone(),
    month: sameDay ? undefined : 'short',
    day: sameDay ? undefined : '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(dt);
}

function chartXAxisOptions(): any {
  return {
    title: { display: true, text: 'Time' },
    ticks: {
      maxTicksLimit: 8,
      maxRotation: 0,
      callback: (_value: unknown, index: number, ticks: unknown[]) => {
        const row = activeRows[index];
        return row ? formatChartAxisLabel(row.datetime) : '';
      },
    },
    grid: { color: 'rgba(148, 163, 184, 0.15)' },
  };
}

function chartCommonOptions(): any {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    animation: { duration: 380 },
    plugins: {
      legend: { labels: { usePointStyle: true, boxWidth: 8 } },
      tooltip: { backgroundColor: '#0f172a', titleColor: '#f8fafc', bodyColor: '#f8fafc', callbacks: { title: (items: any[]) => { const idx = items?.[0]?.dataIndex; const row = typeof idx === 'number' ? activeRows[idx] : null; return row ? formatDateTime(row.datetime) : ''; } } },
    },
  };
}

function renderCharts(data: DataRow[]): void {
  if (data.length === 0) {
    if (speedChart) speedChart.destroy();
    if (weatherChart) weatherChart.destroy();
    speedChart = null;
    weatherChart = null;
    chartsGrid.classList.add('hidden');
    chartEmpty.classList.remove('hidden');
    return;
  }

  chartsGrid.classList.remove('hidden');
  chartEmpty.classList.add('hidden');
  const labels = data.map((row) => row.datetime);
  const speeds = data.map((row) => (row.speed == null ? null : Number(row.speed)));
  const temperatures = data.map((row) => (row.temperature == null ? null : Number(row.temperature)));
  const pressures = data.map((row) => (row.pressure == null ? null : Number(row.pressure)));

  if (speedChart) speedChart.destroy();
  if (weatherChart) weatherChart.destroy();

  const speedCtx = speedChartCanvas.getContext('2d');
  const weatherCtx = weatherChartCanvas.getContext('2d');
  if (!speedCtx || !weatherCtx) return;

  const speedGradient = speedCtx.createLinearGradient(0, 0, 0, 260);
  speedGradient.addColorStop(0, 'rgba(8,145,178,0.32)');
  speedGradient.addColorStop(1, 'rgba(8,145,178,0.02)');

  speedChart = new Chart(speedCtx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Wind speed (m/s)',
        data: speeds,
        borderColor: '#0891b2',
        backgroundColor: speedGradient,
        fill: true,
        tension: 0.32,
        borderWidth: 2.6,
        pointRadius: 1.4,
        pointHoverRadius: 4,
        spanGaps: true,
      }],
    },
    options: {
      ...chartCommonOptions(),
      scales: {
        x: chartXAxisOptions(),
        y: { title: { display: true, text: 'm/s' } },
      },
    },
  });

  weatherChart = new Chart(weatherCtx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Temperature (°C)',
          data: temperatures,
          borderColor: '#dc2626',
          yAxisID: 'yTemp',
          tension: 0.3,
          borderWidth: 2.2,
          pointRadius: 1.4,
          pointHoverRadius: 4,
          spanGaps: true,
        },
        {
          label: 'Pressure (hPa)',
          data: pressures,
          borderColor: '#7c3aed',
          yAxisID: 'yPress',
          tension: 0.3,
          borderWidth: 2.2,
          pointRadius: 1.4,
          pointHoverRadius: 4,
          spanGaps: true,
        },
      ],
    },
    options: {
      ...chartCommonOptions(),
      scales: {
        x: chartXAxisOptions(),
        yTemp: { type: 'linear', position: 'left', title: { display: true, text: '°C' } },
        yPress: { type: 'linear', position: 'right', title: { display: true, text: 'hPa' }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function prepareTimeline(data: DataRow[]): void {
  rowsByTimestamp = new Map<string, DataRow[]>();
  for (const row of data) {
    const bucket = rowsByTimestamp.get(row.datetime) ?? [];
    bucket.push(row);
    rowsByTimestamp.set(row.datetime, bucket);
  }

  timelineFrames = Array.from(rowsByTimestamp.keys()).sort();
  timeline.min = '0';
  timeline.max = String(Math.max(0, timelineFrames.length - 1));
  timeline.value = '0';
  timeline.disabled = timelineFrames.length === 0;

  if (timelineFrames.length > 0) drawFrame(timelineFrames[0]);
  else timelineLabel.textContent = 'No frames';
}

function stopPlayback(): void {
  if (playingTimer != null) {
    window.clearInterval(playingTimer);
    playingTimer = null;
  }
  playButton.textContent = 'Play';
}

function startPlayback(): void {
  if (timelineFrames.length === 0) return;
  playButton.textContent = 'Pause';
  playingTimer = window.setInterval(() => {
    const next = (Number(timeline.value) + 1) % timelineFrames.length;
    timeline.value = String(next);
    drawFrame(timelineFrames[next]);
  }, 900);
}

function renderTable(data: DataRow[]): void {
  output.innerHTML = '';
  if (data.length === 0) {
    renderEmptyRow(output, 9, 'No data points returned for this selection. Try widening date range or selecting aggregation none/hourly.');
    return;
  }
  for (const row of data) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${row.stationName}</td><td title="${row.datetime}">${formatDateTime(row.datetime)}</td><td>${row.temperature ?? ''}</td><td>${row.pressure ?? ''}</td><td>${row.speed ?? ''}</td><td>${row.direction ?? ''}</td><td>${row.latitude ?? ''}</td><td>${row.longitude ?? ''}</td><td>${row.altitude ?? ''}</td>`;
    output.appendChild(tr);
  }
}

async function runQuery(): Promise<void> {
  avgOutput.innerHTML = '';
  statusEl.textContent = 'Loading...';
  stopPlayback();
  setLoading(true);

  const start = toApiDateTime(startInput.value);
  const end = toApiDateTime(endInput.value);
  const station = (document.getElementById('station') as HTMLSelectElement).value;
  const location = locationSelect.value;
  const aggregation = (document.getElementById('aggregation') as HTMLSelectElement).value;

  if (!start || !end) {
    statusEl.textContent = 'Please choose valid start/end datetimes.';
    setLoading(false);
    return;
  }
  if (new Date(start) >= new Date(end)) {
    statusEl.textContent = 'Start datetime must be before end datetime.';
    setLoading(false);
    return;
  }

  const params = new URLSearchParams({ location, aggregation });
  for (const type of selectedTypes()) params.append('types', type);

  const queryPath = `fechaini/${start}/fechafin/${end}/estacion/${station}`;
  const queryParams = params.toString();
  const url = `/api/antartida/datos/${queryPath}?${queryParams}`;

  try {
    const response = await fetch(url);
    const json = await response.json();

    if (!response.ok) {
      statusEl.textContent = 'Request failed';
      alert(json.detail ?? 'Request failed');
      return;
    }

    const data = json.data as DataRow[];
    activeRows = data;
    lastQueryBasePath = queryPath;
    lastQueryParams = queryParams;

    renderTable(data);
    renderAverages(data);
    renderCharts(data);
    renderMetrics(data);
    prepareTimeline(data);
    const mapped = data.filter((r) => r.latitude != null && r.longitude != null).length;
    renderSummary(data.length, mapped);
    if (data.length === 0) {
      setEmptyState(true, 'No records in this window. Adjust station, date range, or aggregation.');
      statusEl.textContent = 'No records returned.';
      timeline.disabled = true;
      playButton.disabled = true;
    } else {
      setEmptyState(false, '');
      playButton.disabled = false;
      statusEl.textContent = `Loaded ${data.length} rows. API location: ${location}. Display timezone: ${uiTimeZone()}.`;
      if (mapped === 0) setEmptyState(true, 'Data loaded but no coordinates available for map overlay.');
    }
    exportCsvBtn.disabled = data.length === 0;
    exportParquetBtn.disabled = data.length === 0;
  } catch (error) {
    statusEl.textContent = 'Network error while requesting data.';
    setEmptyState(true, 'Unable to load data due to a network error.');
    alert('Network error while requesting data.');
  } finally {
    setLoading(false);
  }
}

rangeButtons.forEach((btn) => {
  btn.addEventListener('click', () => applyQuickRange(btn.dataset.range || '6h'));
});

timeline.addEventListener('input', () => {
  const idx = Number(timeline.value);
  if (timelineFrames[idx]) drawFrame(timelineFrames[idx]);
});

playButton.addEventListener('click', () => {
  if (playingTimer == null) startPlayback();
  else stopPlayback();
});

displayTimezoneSelect.addEventListener('change', () => {
  if (activeRows.length === 0) return;
  renderTable(activeRows);
  renderCharts(activeRows);
  renderSummary(activeRows.length, activeRows.filter((r) => r.latitude != null && r.longitude != null).length);
  const idx = Number(timeline.value);
  if (timelineFrames[idx]) drawFrame(timelineFrames[idx]);
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runQuery();
});

setDefaultRange();
locationSelect.value = 'UTC';
displayTimezoneSelect.value = 'Europe/Madrid';
renderMetrics([]);
renderTable([]);
renderAverages([]);
renderCharts([]);
setEmptyState(true, 'Run a query to load weather records and map overlays.');
playButton.disabled = true;

exportCsvBtn.addEventListener('click', async () => {
  await downloadExport('csv');
});

exportParquetBtn.addEventListener('click', async () => {
  await downloadExport('parquet');
});
