export function dashboardChartsTemplate(): string {
  return `
    <section id="charts-section" class="charts-grid hidden">
      <article id="wind-chart-card" class="card chart-card">
        <h2>Wind Speed Timeline</h2>
        <div class="chart-shell"><canvas id="wind-chart"></canvas></div>
      </article>
      <article id="weather-chart-card" class="card chart-card">
        <h2>Selected Station Temperature / Pressure</h2>
        <div class="chart-shell"><canvas id="weather-chart"></canvas></div>
      </article>
      <article id="rose-chart-card" class="card chart-card">
        <h2>Wind Direction Compass (toward flow)</h2>
        <div class="chart-shell"><canvas id="rose-chart"></canvas></div>
      </article>
    </section>
  `;
}
