/* Read-only activity and evaluation views. */
window.MaintenanceUI = (() => {
  const D = MaintenanceData;
  let runs = [];
  let bundle = {};
  let runFilter = "all";
  let caseFilter = "priority";

  const uiMap = {
    "未记录": "Not recorded", "真实模型": "Live model", "规则演练": "Rule demo",
    "确定性操作": "Deterministic", "失败": "Failed", "部分完成": "Partial",
    "已跳转": "Opened", "执行完成": "Complete", "入口已创建": "Links ready",
    "通过": "Pass", "未运行": "Not run", "改善": "Improved", "退步": "Regressed",
    "未变化": "Unchanged", "不可比较": "Not comparable", "仍失败": "Still failing",
    "回归退步": "Regression", "待处理": "Open", "已修复": "Fixed",
    "开发集": "Development", "保留验证集": "Holdout"
  };
  const toolNames = {
    get_task: "Read task", get_preferences: "Read preferences",
    update_item: "Update item", update_constraints: "Update constraints",
    search_products: "Search products", read_evidence: "Read evidence",
    set_plan: "Set plan", check_plan: "Check plan"
  };
  const assertionLabels = {
    budget: "Budget", no_confirmation: "No purchase confirmation",
    count: "Item count", categories: "Categories", exclusions: "Exclusions",
    quantity: "Quantity", clarify: "Clarification", unknown: "Unknown costs",
    compatibility: "Compatibility", expected_error: "Expected error",
    min: "Minimum items", max: "Maximum items", forbid_categories: "Excluded categories",
    owned: "Owned items", required_offer: "Required offer", optional: "Optional offer"
  };
  const display = value => uiMap[value] || value;
  const cleanDate = value => display(D.date(value, true));
  const safeUrl = value => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password ? esc(url.href) : "";
    } catch { return ""; }
  };
  const text = value => {
    if (value === null || value === undefined || value === "") return "Not recorded";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (Array.isArray(value)) return value.length ? value.map(text).join(" · ") : "None";
    if (typeof value === "object") {
      return Object.entries(value).map(([key, item]) =>
        (assertionLabels[key] || key) + ": " + text(item)).join(" · ");
    }
    return display(String(value));
  };
  const tag = value => {
    const shown = display(value);
    const bad = ["Failed", "Regressed", "Still failing", "Regression"].includes(shown);
    const good = ["Pass", "Improved", "Complete", "Links ready", "Fixed"].includes(shown);
    return '<span class="state ' + (bad ? "bad" : good ? "good" : "neutral") + '">' +
      esc(shown) + '</span>';
  };
  const page = (title, content, action = "") =>
    '<div class="maintenance-page"><div class="maint-title"><h1>' + esc(title) +
    '</h1>' + action + '</div>' + content + '</div>';
  const section = (title, content) =>
    '<section class="surface detail-section"><h2>' + esc(title) + '</h2>' + content + '</section>';
  const kv = rows => '<dl class="kv">' + rows.map(([key, value]) =>
    '<div><dt>' + esc(key) + '</dt><dd>' + esc(text(value)) + '</dd></div>').join("") + '</dl>';
  const long = value => '<p class="long-text">' + esc(text(value)) + '</p>';
  const artifactLinks = items => '<footer class="artifact-links">' + items.map(([label, id]) =>
    '<a href="/files/' + encodeURIComponent(id) + '">' + esc(label) + ' ↧</a>').join("") + '</footer>';
  const outcome = row => display(D.outcome(row));

  function runMode(row) { return display(D.mode(row)); }
  function runStatus(row) { return display(D.status(row)); }
  function runOperation(row) {
    if (row.type === "purchase_jump") return "Open purchase link";
    if (row.type === "checkout") {
      return D.arr(row.entries).some(item => item.kind === "local_demo") ?
        "Checkout rehearsal" : "Prepare checkout";
    }
    return row.input || "Recorded operation";
  }

  function renderRuns() {
    const filtered = runFilter === "all" ? runs : runs.filter(row =>
      runFilter === "failed" ? row.status === "failed" : runMode(row) === runFilter);
    const stats = D.runStats(filtered);
    const taskNames = new Map(boot.tasks.map(item => [item.id,
      item.title === "新的采购任务" ? "New list" : item.title]));
    const controls = '<div class="filters"><label class="filter-label">Show<select id="run-filter">' +
      [["all", "All activity"], ["failed", "Failed"], ["Live model", "Live model"],
       ["Rule demo", "Rule demo"], ["Deterministic", "Deterministic"]]
        .map(([value, label]) => '<option value="' + esc(value) + '" ' +
          (runFilter === value ? "selected" : "") + '>' + esc(label) + '</option>').join("") +
      '</select></label></div>';
    const metrics = '<div class="metrics compact"><article><span>Records</span><strong>' +
      stats.count + '</strong><small>Current filter</small></article><article><span>Failures</span><strong>' +
      stats.failed + '</strong><small>Recorded failures</small></article><article><span>Median time</span><strong>' +
      D.duration(stats.median) + '</strong><small>' + stats.timed + ' timed</small></article></div>';
    const table = filtered.length ? '<div class="table-wrap"><table class="records"><thead><tr>' +
      '<th>Time</th><th>Task / operation</th><th>Mode</th><th>Status</th><th>Duration</th><th></th>' +
      '</tr></thead><tbody>' + filtered.map(row => '<tr><td data-label="Time">' +
      cleanDate(row.created) + '</td><td data-label="Task / operation" class="summary-cell"><strong>' +
      esc(runOperation(row)) + '</strong><small>' +
      esc(taskNames.get(row.task_id) || "Task not available") + '</small></td><td data-label="Mode">' +
      esc(runMode(row)) + '</td><td data-label="Status">' + tag(runStatus(row)) +
      '</td><td data-label="Duration">' + D.duration(row.latency_ms) +
      '</td><td><a href="/runs/' + esc(row.id) + '" data-nav="/runs/' +
      esc(row.id) + '">View →</a></td></tr>').join("") + '</tbody></table></div>' :
      '<div class="empty-state"><h2>No matching activity</h2><p>Runs will appear here.</p></div>';
    $("#main").innerHTML = page("Activity", controls + metrics + '<section class="surface">' + table + '</section>');
    $("#run-filter")?.addEventListener("change", event => {
      runFilter = event.target.value;
      renderRuns();
    });
  }

  function eventResult(event) {
    if (event.error) return event.error;
    const result = event.result;
    if (Array.isArray(result)) return result.length + " result" + (result.length === 1 ? "" : "s");
    if (result?.items) return result.items.length + " plan item" + (result.items.length === 1 ? "" : "s");
    if (result?.product) return result.product.name;
    return result?.status || "Complete";
  }

  async function renderRunDetail(id) {
    const row = await api("/api/run/" + id);
    const calls = D.callInfo(row);
    const trace = D.arr(row.events);
    const evidence = D.evidence(row);
    const timeline = trace.length ? '<ol class="timeline">' + trace.map((event, index) =>
      '<li><span class="timeline-index">' + String(index + 1).padStart(2, "0") +
      '</span><div><strong>' + esc(toolNames[event.tool] || event.tool || "Step") +
      '</strong><small>' + esc(event.status || (event.error ? "Failed" : "Complete")) +
      ' · ' + D.duration(event.latency_ms) + '</small><p>' + esc(eventResult(event)) +
      '</p></div></li>').join("") + '</ol>' : '<p class="muted">No tool events recorded.</p>';
    const productEvidence = evidence.length ? '<div class="evidence-grid">' + evidence.map(snapshot =>
      '<article><h3>' + esc(snapshot.product.name) + '</h3><p>' +
      esc(snapshot.variant?.spec || "Specification unavailable") + '</p><small>' +
      esc(snapshot.offer?.merchant || "Seller unavailable") + '</small>' +
      D.arr(snapshot.product.evidence).map(item => '<p>' + esc(item.excerpt || "No excerpt") +
        (safeUrl(item.url) ? ' <a href="' + safeUrl(item.url) +
          '" target="_blank" rel="noopener">Source ↗</a>' : "") + '</p>').join("") +
      '</article>').join("") + '</div>' : '<p class="muted">No product evidence recorded.</p>';
    const content =
      '<div class="detail-meta">' + tag(runStatus(row)) + '<span>' +
      esc(runMode(row)) + '</span><span>' + cleanDate(row.started_at || row.created) + '</span></div>' +
      section("Overview", kv([
        ["Run ID", row.id || id], ["Task", row.task_id],
        ["Input", runOperation(row)], ["Duration", D.duration(row.latency_ms)],
        ["Model", row.model], ["Strategy", row.strategy?.version || row.prompt_version]
      ])) +
      section("Tool timeline", timeline) +
      section("Product evidence", productEvidence) +
      section("Usage", kv([
        ["Model calls", calls.calls], ["Tokens", calls.tokens], ["Estimated cost", calls.cost],
        ["Tool calls", row.tool_calls], ["Retries", row.retries], ["Failure", row.error]
      ])) +
      '<footer class="artifact-links"><a href="/downloads/run/' + esc(id) +
      '">Download record ↧</a></footer>';
    $("#main").innerHTML = page("Run detail", content,
      '<a href="/runs" data-nav="/runs">← Activity</a>');
  }

  function badcaseRows() {
    const source = D.arr(bundle.badcases?.cases);
    const priority = ["仍失败", "回归退步", "待处理"];
    const rows = caseFilter === "all" ? source :
      caseFilter === "priority" ? source.filter(item => priority.includes(item.status)) :
      source.filter(item => item.status === caseFilter);
    return {source, rows};
  }

  function renderBadcasePanel() {
    const {source, rows} = badcaseRows();
    if (!source.length) return "";
    const counts = ["待处理", "已修复", "仍失败", "回归退步"].map(status =>
      '<span>' + esc(display(status)) + ' <b>' +
      source.filter(item => item.status === status).length + '</b></span>').join("");
    return '<section class="surface detail-section"><div class="section-head"><h2>Bad cases</h2>' +
      '<label class="filter-label">Show<select id="badcase-filter">' +
      [["priority", "Priority"], ["all", "All"], ["待处理", "Open"], ["已修复", "Fixed"],
       ["仍失败", "Still failing"], ["回归退步", "Regressions"]]
        .map(([value, label]) => '<option value="' + esc(value) + '" ' +
          (caseFilter === value ? "selected" : "") + '>' + esc(label) + '</option>').join("") +
      '</select></label></div><div class="change-counts">' + counts + '</div>' +
      '<div class="table-wrap"><table class="records badcase-table"><thead><tr>' +
      '<th>Case</th><th>Layer</th><th>Root cause</th><th>Status</th><th></th></tr></thead><tbody>' +
      rows.map(item => '<tr><td data-label="Case" class="summary-cell"><strong>' +
        esc(item.id) + '</strong><small>' + esc(text(item.phenomenon)) +
        '</small></td><td data-label="Layer">' + esc(text(item.layer)) +
        '</td><td data-label="Root cause" class="summary-cell">' +
        esc(text(item.root_cause)) + '<small>' + esc(text(item.confidence)) +
        '</small></td><td data-label="Status">' + tag(item.status) +
        '</td><td><a href="/evaluation/badcase/' + esc(item.id) +
        '" data-nav="/evaluation/badcase/' + esc(item.id) + '">Review →</a></td></tr>'
      ).join("") + '</tbody></table></div></section>';
  }

  function metricCards(report) {
    const summaries = report.summaries || {};
    const keys = Object.keys(summaries);
    if (!keys.length) {
      return '<div class="metrics"><article><span>System tests</span><strong>' +
        esc(report.system?.passed ?? "—") + '<small> / ' +
        esc(report.system?.total ?? "—") + '</small></strong></article></div>';
    }
    return '<div class="metrics">' + keys.slice(-3).map(version => {
      const value = summaries[version] || {};
      return '<article><span>' + esc(version.toUpperCase()) + '</span><strong>' +
        esc(value.passed ?? value.success ?? "—") + '<small> / ' +
        esc(value.total ?? "—") + '</small></strong><small>' +
        esc(display(value.mode || "Recorded evaluation")) + '</small></article>';
    }).join("") + '</div>';
  }

  function renderComparison(report) {
    const versions = Object.keys(report.rows || {});
    if (!versions.length) return section("Case results", '<p class="muted">No case rows recorded.</p>');
    const left = versions[0];
    const right = versions.at(-1);
    const comparison = D.compare(report, bundle.cases, left, right, "all");
    const rows = comparison.rows;
    const table = '<div class="table-wrap"><table class="records case-table"><thead><tr>' +
      '<th>Case</th><th>Scenario</th><th>' + esc(left) + '</th><th>' + esc(right) +
      '</th><th>Change</th><th></th></tr></thead><tbody>' + rows.map(item =>
      '<tr><td data-label="Case">' + esc(item.id) + '</td><td data-label="Scenario" class="summary-cell">' +
      esc(item.case?.name || "Scenario") + '</td><td data-label="' + esc(left) + '">' +
      tag(item.leftStatus) + '</td><td data-label="' + esc(right) + '">' +
      tag(item.rightStatus) + '</td><td data-label="Change">' + tag(item.change) +
      '</td><td><a href="/evaluation/' + encodeURIComponent(item.id) +
      '" data-nav="/evaluation/' + encodeURIComponent(item.id) + '">View →</a></td></tr>'
    ).join("") + '</tbody></table></div>';
    const note = comparison.comparable
      ? right + " changed by " + (comparison.points >= 0 ? "+" : "") +
        comparison.points.toFixed(1) + " percentage points."
      : "Some rows are not directly comparable; each result remains visible.";
    return section("Version comparison", '<p class="comparison-note">' + esc(note) + '</p>' + table);
  }

  function renderLiveReports() {
    const reports = D.arr(bundle.live_reports);
    if (!reports.length) return section("Model evaluations", '<p class="muted">No model evaluation has been recorded.</p>');
    return section("Model evaluations", '<div class="table-wrap"><table class="records"><thead><tr>' +
      '<th>Batch</th><th>Model</th><th>Created</th><th>Cases</th><th>Mode</th></tr></thead><tbody>' +
      reports.map(report => '<tr><td data-label="Batch">' +
        esc(report.id || report.run_id || "Recorded batch") + '</td><td data-label="Model">' +
        esc(report.model || "Not recorded") + '</td><td data-label="Created">' +
        cleanDate(report.created || report.started_at) + '</td><td data-label="Cases">' +
        D.arr(report.results || report.rows).length + '</td><td data-label="Mode">' +
        esc(display(report.execution || report.mode || "Recorded")) +
        '</td></tr>').join("") + '</tbody></table></div>');
  }

  function renderEvaluation() {
    const report = bundle.report;
    if (!report) {
      $("#main").innerHTML = page("Evaluation",
        '<section class="surface empty-state"><h2>No report yet</h2><p>Run an evaluation to populate this page.</p></section>');
      return;
    }
    const links = artifactLinks([
      ["Evaluation report", "report"], ["Benchmark cases", "cases"],
      ["V1 strategy", "strategy-v1"], ["V2 strategy", "strategy-v2"],
      ["Evaluation code", "evaluation-code"], ["Acceptance notes", "acceptance"]
    ]);
    $("#main").innerHTML = page("Evaluation",
      renderBadcasePanel() + metricCards(report) + renderComparison(report) +
      renderLiveReports() + section("Report identity", kv([
        ["Created", cleanDate(report.created)], ["Benchmark", report.test_set],
        ["Catalog", report.catalog_version], ["Commit", report.commit],
        ["External checkout", report.external_checkout], ["Transactions", report.real_transactions]
      ])) + links);
    $("#badcase-filter")?.addEventListener("change", event => {
      caseFilter = event.target.value;
      renderEvaluation();
    });
  }

  function renderBadcase(id) {
    const item = D.arr(bundle.badcases?.cases).find(row => row.id === id);
    if (!item) {
      $("#main").innerHTML = page("Bad case", '<p>This case is not available.</p>',
        '<a href="/evaluation" data-nav="/evaluation">← Evaluation</a>');
      return;
    }
    const fields = [
      ["Input and context", item.input], ["Expected", item.expected], ["Actual", item.actual],
      ["User impact", item.impact], ["Failure layer", item.layer], ["Root cause", item.root_cause],
      ["Confidence", item.confidence], ["Cause, trigger, symptom", item.cause_vs_trigger],
      ["Fix", item.fix], ["Fix layer", item.fix_layer], ["Why this layer", item.why],
      ["Retest", item.verification], ["Regression checks", item.regression], ["Remaining risk", item.risk]
    ];
    const evidence = '<ul class="plain-list">' + D.arr(item.evidence).map(value =>
      '<li>' + esc(text(value)) + '</li>').join("") + '</ul>';
    $("#main").innerHTML = page(item.id + " · " + text(item.phenomenon),
      '<div class="detail-meta">' + tag(item.status) + '<span>' +
      esc(text(item.versions)) + '</span></div>' +
      section("Evidence", evidence) + fields.map(([label, value]) =>
        section(label, long(value))).join(""),
      '<a href="/evaluation" data-nav="/evaluation">← Evaluation</a>');
  }

  function findCase(id) {
    const report = bundle.report || {};
    const versions = Object.keys(report.rows || {});
    const dataset = D.arr(bundle.cases).find(item => item.id === id);
    return {report, versions, dataset,
      rows: versions.map(version => [version,
        D.arr(report.rows?.[version]).find(item => item.id === id)])};
  }

  function assertions(row) {
    if (!row) return '<p class="muted">No run.</p>';
    const source = row.assertions || row.checks || {};
    const entries = Object.entries(source);
    if (!entries.length) return '<p>' + tag(D.outcome(row)) + '</p>';
    return '<ul class="assertions">' + entries.map(([key, value]) =>
      '<li>' + tag(value === true ? "通过" : value === false ? "失败" : "未运行") +
      ' ' + esc(assertionLabels[key] || key) + '</li>').join("") + '</ul>';
  }

  function renderCase(id) {
    const {report, versions, dataset, rows} = findCase(id);
    if (!rows.some(([, row]) => row)) {
      $("#main").innerHTML = page("Case detail", '<p>This case is not available.</p>',
        '<a href="/evaluation" data-nav="/evaluation">← Evaluation</a>');
      return;
    }
    const cards = rows.map(([version, row]) =>
      '<section class="surface detail-section"><div class="section-head"><h2>' +
      esc(version) + '</h2>' + tag(D.outcome(row)) + '</div><h3>Output</h3>' +
      long(row?.output || row?.response || row?.error || "Not recorded") +
      '<h3>Checks</h3>' + assertions(row) + '<h3>Trace</h3><ol class="plain-list">' +
      D.arr(row?.traces).flatMap(trace => D.arr(trace.events)).map(event =>
        '<li>' + esc(toolNames[event.tool] || event.tool || "Step") + ' · ' +
        esc(eventResult(event)) + '</li>').join("") + '</ol></section>'
    ).join("");
    $("#main").innerHTML = page("Case " + id,
      section("Scenario", kv([
        ["Name", dataset?.name], ["Group", dataset?.split],
        ["Expected behavior", dataset?.expected], ["Hard constraints", dataset?.constraints]
      ])) + '<div class="detail-grid">' + cards + '</div>' +
      artifactLinks([["Evaluation report", "report"], ["Benchmark cases", "cases"]]),
      '<a href="/evaluation" data-nav="/evaluation">← Evaluation</a>');
  }

  async function route(path) {
    if (!runs.length) runs = await api("/api/runs");
    if (!Object.keys(bundle).length) bundle = await api("/api/maintenance");
    if (path === "/runs") return renderRuns();
    if (path.startsWith("/runs/")) return renderRunDetail(path.split("/").pop());
    if (path === "/evaluation") return renderEvaluation();
    if (path.startsWith("/evaluation/badcase/")) return renderBadcase(decodeURIComponent(path.split("/").pop()));
    if (path.startsWith("/evaluation/")) return renderCase(decodeURIComponent(path.split("/").pop()));
  }

  return {route};
})();
