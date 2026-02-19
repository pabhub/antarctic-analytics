export function stationWorkspaceTemplate(): string {
  return `
    <article class="card map-card">
      <div class="section-head">
        <h2>Station Workspace</h2>
      </div>
      <div class="map-frame">
        <div class="map-selector-panel">
          <div class="map-selector-grid">
            <label>
              Antarctic Station
              <select id="station" required>
                <option value="">Loading stations...</option>
              </select>
            </label>
            <label>
              History window
              <select id="history-years">
                <option value="2" selected>2 years</option>
                <option value="3">3 years</option>
                <option value="5">5 years</option>
                <option value="10">10 years</option>
              </select>
            </label>
          </div>
        </div>
        <div id="map-canvas"></div>
        <div id="query-progress-wrap" class="progress-wrap map-progress-wrap">
          <progress id="query-progress-bar" value="0" max="1"></progress>
          <p id="query-progress-text" class="muted">Waiting for job...</p>
        </div>
      </div>
      <div id="map-playback-shell" class="map-playback-shell hidden">
        <div class="map-playback-head">
          <h3>Wind Playback</h3>
          <p id="playback-window-label" class="muted"></p>
        </div>
        <div class="playback-toolbar">
          <div class="playback-primary">
            <button id="playback-play" type="button" class="secondary icon-btn playback-icon-btn" disabled aria-label="Play playback">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 6v12l10-6-10-6z" fill="currentColor"></path>
              </svg>
              <span class="sr-only">Play</span>
            </button>
            <label class="inline-label playback-loop"><input id="playback-loop" type="checkbox" checked />Loop</label>
          </div>
          <label class="playback-field">Step
            <select id="playback-step">
              <option value="10m">10m</option>
              <option value="1h" selected>1h</option>
              <option value="3h">3h</option>
              <option value="1d">1d</option>
            </select>
          </label>
          <label class="playback-field">Speed
            <select id="playback-speed">
              <option value="1x" selected>1x</option>
              <option value="4x">4x</option>
              <option value="10x">10x</option>
              <option value="20x">20x</option>
              <option value="40x">40x</option>
              <option value="80x">80x</option>
              <option value="120x">120x</option>
            </select>
          </label>
          <div class="overlay-toggles playback-toggles-inline">
            <label class="inline-label"><input id="overlay-temperature" type="checkbox" />Temperature halo</label>
            <label class="inline-label"><input id="overlay-pressure" type="checkbox" />Pressure ring</label>
            <label class="inline-label"><input id="overlay-trail" type="checkbox" checked />Direction trail</label>
          </div>
        </div>
        <input id="playback-slider" type="range" min="0" max="0" value="0" />
        <p id="playback-status" class="muted playback-status-line" title=""></p>

        <div id="playback-progress-wrap" class="progress-wrap playback-progress-wrap">
          <progress id="playback-progress-bar" value="0" max="1"></progress>
          <p id="playback-progress-text" class="muted">Frames 0/0.</p>
        </div>
      </div>
      <div id="status-panel" class="status status-info">
        <p id="status" class="status-line">Bootstrapping Antarctic cache...</p>
      </div>
      <p id="error-banner" class="status status-error hidden"></p>
    </article>
  `;
}
