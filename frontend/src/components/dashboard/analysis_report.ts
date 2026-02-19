export function analysisReportTemplate(): string {
  return `
    <article id="decision-card" class="card hidden">
      <div class="section-head">
        <div class="analysis-title-row">
          <h2>Analysis & Recommendations Report</h2>
          <span id="decision-badge" class="decision-badge">Screening</span>
        </div>
        <p id="decision-updated" class="muted"></p>
      </div>

      <section class="analysis-block">
        <h3>Current Window Snapshot</h3>
        <section id="metrics-grid" class="metrics-grid"></section>
        <div class="decision-grid">
          <article class="decision-tile">
            <h3>Wind Resource Signal</h3>
            <p id="decision-wind"></p>
          </article>
          <article class="decision-tile">
            <h3>Data Quality & Coverage</h3>
            <p id="decision-quality"></p>
          </article>
          <article class="decision-tile">
            <h3>Operational Implications</h3>
            <p id="decision-risk"></p>
          </article>
        </div>
      </section>

      <section id="timeframe-section" class="analysis-block hidden">
        <div class="analysis-subhead">
          <h3>Loaded Years Comparison</h3>
          <p class="muted">Grouping uses loaded station history from the selected map station. Missing year/period values are shown as "-".</p>
        </div>
        <div class="timeframe-controls">
          <label>Compare by
            <select id="timeframe-grouping">
              <option value="month" selected>Month</option>
              <option value="season">Season</option>
            </select>
          </label>
          <label class="timeframe-action">
            <span class="timeframe-action-label" aria-hidden="true">Action</span>
            <button id="timeframe-run" type="button">Run analysis</button>
          </label>
        </div>
        <p id="timeframe-status" class="timeframe-status timeframe-status-info">Ready to compare loaded years.</p>
        <p id="generation-summary" class="muted">Configure wind farm parameters in Config page to calculate expected generation with air-density and operating-envelope correction.</p>
        <div id="timeframe-trend-wrap" class="timeframe-trend-wrap hidden">
          <h3>Timeframe Min / Avg / Max Trends</h3>
          <div class="chart-shell timeframe-chart-shell"><canvas id="timeframe-trend-chart"></canvas></div>
        </div>
        <div id="timeframe-cards" class="timeframe-cards"></div>
        <div id="timeframe-comparison" class="comparison-grid"></div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th id="timeframe-period-column">Period</th>
                <th>Start</th>
                <th>End</th>
                <th>Data Points</th>
                <th>Min Speed</th>
                <th>Avg Speed</th>
                <th>Max Speed</th>
                <th>P90 (90th pct)</th>
                <th>Hours ≥ 3</th>
                <th>Hours ≥ 5</th>
                <th>Variability</th>
                <th>Dominant Heading</th>
                <th>Avg Temp</th>
                <th>Avg Pressure</th>
                <th>Generation (MWh)</th>
              </tr>
            </thead>
            <tbody id="timeframe-output"></tbody>
          </table>
        </div>
      </section>
    </article>
  `;
}
