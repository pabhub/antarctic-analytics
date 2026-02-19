import { renderPageRoot } from "../render.js";
import { complianceFooterTemplate } from "../layout/footer.js";
import { topNavTemplate } from "../layout/top_nav.js";
import { analysisReportTemplate } from "./analysis_report.js";
import { dashboardChartsTemplate } from "./charts.js";
import { dashboardHeroTemplate } from "./hero.js";
import { rawTablesTemplate } from "./raw_tables.js";
import { resultsSkeletonTemplate } from "./results_skeleton.js";
import { stationWorkspaceTemplate } from "./station_workspace.js";

export function dashboardPageTemplate(): string {
  return `
    ${topNavTemplate({
      active: "dashboard",
      brand: "GS Inima · Antarctic Wind Feasibility",
      showAuth: true,
    })}
    <div class="app-toast-wrap">
      <div id="app-toast" class="app-toast hidden" role="status" aria-live="polite">
        <p id="app-toast-text">Analysis ready.</p>
        <button id="app-toast-close" type="button" class="app-toast-close secondary" aria-label="Close notification">✕</button>
      </div>
    </div>
    <main class="container">
      ${dashboardHeroTemplate()}
      <section class="content-stack">
        ${stationWorkspaceTemplate()}
        ${resultsSkeletonTemplate()}
        ${dashboardChartsTemplate()}
        ${analysisReportTemplate()}
        ${rawTablesTemplate()}
      </section>
    </main>
    ${complianceFooterTemplate()}
  `;
}

export function renderDashboardPage(): void {
  renderPageRoot(dashboardPageTemplate());
}
