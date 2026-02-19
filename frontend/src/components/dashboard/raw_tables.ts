export function rawTablesTemplate(): string {
  return `
    <article id="raw-card" class="card hidden">
      <div class="section-head">
        <h2>Raw Data Tables</h2>
        <div class="table-head-actions">
          <div class="export-icon-actions" aria-label="Download exports">
            <button type="button" id="export-csv" class="secondary icon-btn" title="Download CSV" aria-label="Download CSV">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M8 3h6l5 5v11a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm5 1.5V9h4.5M8 15h8M8 12h8M8 18h5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span class="sr-only">Download CSV</span>
            </button>
            <button type="button" id="export-parquet" class="secondary icon-btn" title="Download Parquet" aria-label="Download Parquet">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M4 8.5 12 4l8 4.5-8 4.5L4 8.5Zm0 7L12 20l8-4.5M4 12l8 4.5 8-4.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span class="sr-only">Download Parquet</span>
            </button>
          </div>
          <button id="toggle-tables" type="button" class="secondary tables-toggle">Show tables</button>
        </div>
      </div>
      <div id="tables-panel" class="collapsed">
        <div class="table-group">
          <h3>Station Feasibility Summary</h3>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Station</th>
                  <th>Data Points</th>
                  <th>Coverage</th>
                  <th>Avg Speed</th>
                  <th>P90 Speed (90th pct)</th>
                  <th>Max Speed</th>
                  <th>Hours ≥ 5 m/s</th>
                  <th>Avg Temp</th>
                  <th>WPD Proxy</th>
                  <th>Latest UTC</th>
                </tr>
              </thead>
              <tbody id="summary-output"></tbody>
            </table>
          </div>
        </div>
        <div class="table-group">
          <h3>Selected Station Detailed Data Points</h3>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Datetime</th>
                  <th>Temperature</th>
                  <th>Pressure</th>
                  <th>Speed</th>
                  <th>Direction</th>
                  <th>Latitude</th>
                  <th>Longitude</th>
                  <th>Altitude</th>
                </tr>
              </thead>
              <tbody id="rows-output"></tbody>
            </table>
          </div>
        </div>
      </div>
    </article>
  `;
}
