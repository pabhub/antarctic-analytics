export function decisionSnapshotTemplate(): string {
  return `
    <article id="decision-card" class="card hidden">
      <div class="section-head">
        <h2>Current Window Snapshot</h2>
        <div class="decision-head-right">
          <p id="decision-updated" class="muted"></p>
          <span id="decision-badge" class="decision-badge">Screening</span>
        </div>
      </div>
      <p class="muted">This card summarizes the currently loaded window. Interannual decision comments are in Loaded Years Comparison.</p>
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
    </article>
  `;
}
