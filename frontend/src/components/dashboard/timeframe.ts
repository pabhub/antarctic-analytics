export function timeframeAnalysisTemplate(): string {
  return `
    <article id="timeframe-card" class="card hidden">
      <h2>Loaded Years Comparison & Decision</h2>
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
      <p class="muted">Grouping uses loaded station history from the selected map station. Missing year/bucket values are shown as "-".</p>
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
              <th>Bucket</th>
              <th>Start</th>
              <th>End</th>
              <th>Rows</th>
              <th>Min Speed</th>
              <th>Avg Speed</th>
              <th>Max Speed</th>
              <th>P90 (90th pct)</th>
              <th>Hours ≥ 3</th>
              <th>Hours ≥ 5</th>
              <th>Variability</th>
              <th>Dominant Dir</th>
              <th>Avg Temp</th>
              <th>Avg Pressure</th>
              <th>Generation (MWh)</th>
            </tr>
          </thead>
          <tbody id="timeframe-output"></tbody>
        </table>
      </div>
    </article>
  `;
}
