// Admin dashboard tiles and reports page (issue #34). Administrators only; the API checks the role.
//   GET /api/admin/reports/summary          dashboard figures (FR-024)
//   GET /api/admin/reports?type=...         basic reports (FR-025)
// Used on two pages: the dashboard (#summary-tiles only) and /admin/reports (everything).
// Every figure is counted live by the API. All text is inserted with textContent.
(function () {
  const STATUS_LABELS = {
    submitted: "Submitted", assigned: "Assigned", in_progress: "In progress",
    resolved: "Resolved", closed: "Closed",
  };
  const message = document.getElementById("message");
  const tiles = document.getElementById("summary-tiles");
  const statusTiles = document.getElementById("status-tiles");
  const rangeForm = document.getElementById("range-form");
  const asOf = document.getElementById("as-of");

  function leaveIfUnauthorized(result) {
    if (result.status === 401) { window.location.href = "/login"; return true; }
    if (result.status === 403) { window.location.href = "/home"; return true; }
    return false;
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function show(text) { if (message) scmsShow(message, text); }

  function range() {
    const params = new URLSearchParams();
    if (rangeForm) {
      for (const name of ["from", "to"]) {
        const value = rangeForm.elements[name].value;
        if (value) params.set(name, value);
      }
    }
    return params;
  }

  function tile(label, value, note) {
    const box = el("div", null, "stat-tile");
    box.append(el("span", label, "stat-label"), el("span", value, "stat-value"));
    if (note) box.appendChild(el("span", note, "stat-note"));
    return box;
  }

  async function loadSummary() {
    if (!tiles) return;
    const result = await scmsApi("GET", "/api/admin/reports/summary?" + range().toString());
    if (leaveIfUnauthorized(result)) return;
    tiles.innerHTML = "";
    if (!result.ok) { tiles.appendChild(el("p", "Could not load the figures: " + scmsErrorMessage(result))); return; }
    const s = result.data;
    const rating = s.feedback.average_rating;
    tiles.append(
      tile("Total complaints", String(s.total)),
      tile("Pending (unresolved)", String(s.pending), "Submitted, assigned or in progress"),
      tile("Waiting for assignment", String(s.unassigned), "Open and not assigned"),
      tile("Average rating", rating === null ? "—" : rating.toFixed(1) + " / 5",
        s.feedback.count + (s.feedback.count === 1 ? " rating" : " ratings")),
    );
    if (statusTiles) {
      statusTiles.innerHTML = "";
      // Lifecycle order, not the (alphabetical) key order of the JSON object.
      for (const status of Object.keys(STATUS_LABELS)) {
        statusTiles.appendChild(tile(STATUS_LABELS[status], String(s.by_status[status] || 0)));
      }
    }
    if (asOf) asOf.textContent = "Figures as of " + new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) + ".";
  }

  // ---------------------------------------------------------------- report tables (reports page only)

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { dateStyle: "medium" });
  }

  function td(text, className) { return el("td", text, className); }

  function fillTable(id, columns, rows, renderRow, footer, emptyText) {
    const table = document.getElementById(id);
    if (!table) return;
    table.innerHTML = "";
    const head = el("thead");
    const headRow = el("tr");
    for (const [label, numeric] of columns) headRow.appendChild(el("th", label, numeric ? "num" : ""));
    head.appendChild(headRow);
    const body = el("tbody");
    if (!rows.length) {
      const empty = td(emptyText || "No complaints in this period.", "muted");
      empty.colSpan = columns.length;
      const tr = el("tr");
      tr.appendChild(empty);
      body.appendChild(tr);
    } else {
      for (const row of rows) body.appendChild(renderRow(row));
    }
    table.append(head, body);
    if (footer && rows.length) {
      const foot = el("tfoot");
      foot.appendChild(footer);
      table.appendChild(foot);
    }
  }

  function totalRow(label, total, extraCells) {
    const tr = el("tr");
    tr.append(td(label), td(String(total), "num"));
    for (const cell of extraCells || []) tr.appendChild(td(cell, "num"));
    return tr;
  }

  function shareRow(label, count, share, extra) {
    const tr = el("tr");
    tr.append(label instanceof Node ? label : td(label), td(String(count), "num"), td(share.toFixed(1) + "%", "num"));
    if (extra !== undefined) tr.appendChild(td(String(extra), "num"));
    return tr;
  }

  async function report(type, extra) {
    const params = range();
    for (const [k, v] of Object.entries(extra || {})) params.set(k, v);
    params.set("type", type);
    const result = await scmsApi("GET", "/api/admin/reports?" + params.toString());
    if (leaveIfUnauthorized(result)) return null;
    if (!result.ok) { show("Could not load the " + type + " report: " + scmsErrorMessage(result)); return null; }
    return result.data;
  }

  async function loadStatus() {
    const data = await report("status");
    if (!data) return;
    fillTable("report-status", [["Status"], ["Complaints", true], ["Share", true]], data.rows,
      (r) => shareRow(r.label, r.count, r.share), totalRow("Total", data.total, ["100%"]));
  }

  async function loadCategory() {
    const data = await report("category");
    if (!data) return;
    fillTable("report-category", [["Category"], ["Complaints", true], ["Share", true]], data.rows,
      (r) => shareRow(r.is_active ? r.label : r.label + " (inactive)", r.count, r.share),
      totalRow("Total", data.total, ["100%"]), "No categories yet.");
  }

  async function loadDepartment() {
    const data = await report("department");
    if (!data) return;
    const openTotal = data.rows.reduce((sum, r) => sum + r.open, 0);
    fillTable("report-department", [["Department"], ["Complaints", true], ["Share", true], ["Open", true]], data.rows,
      (r) => shareRow(r.label, r.count, r.share, r.open), totalRow("Total", data.total, ["100%", String(openTotal)]));
  }

  async function loadPeriod() {
    const group = document.getElementById("period-group").value;
    const data = await report("period", { group });
    if (!data) return;
    fillTable("report-period", [[group === "day" ? "Day" : "Month"], ["Complaints", true], ["Share", true]], data.rows,
      (r) => shareRow(r.period, r.count, r.share), totalRow("Total", data.total, ["100%"]));
  }

  async function loadWorkload() {
    const data = await report("workload");
    if (!data) return;
    fillTable("report-workload",
      [["Staff member"], ["Assigned", true], ["In progress", true], ["Open", true], ["Resolved", true], ["Closed", true]],
      data.rows,
      (r) => {
        const tr = el("tr");
        const who = td(r.staff.name + (r.staff.is_active ? "" : " (inactive)"));
        who.appendChild(el("span", r.department ? r.department.name : "No department", "sub"));
        tr.append(who, td(String(r.assigned), "num"), td(String(r.in_progress), "num"), td(String(r.open), "num"),
          td(String(r.resolved), "num"), td(String(r.closed), "num"));
        return tr;
      }, null, "No maintenance staff yet.");
  }

  async function loadPending() {
    const data = await report("pending");
    if (!data) return;
    fillTable("report-pending", [["Complaint"], ["Status"], ["Category"], ["Assigned to"], ["Submitted"], ["Days open", true]],
      data.rows,
      (r) => {
        const tr = el("tr");
        const title = td(r.title);
        title.appendChild(el("span", r.complaint_id, "sub"));
        const assigned = r.department ? r.department + (r.staff ? " – " + r.staff : "") : "Not assigned";
        tr.append(title, td(STATUS_LABELS[r.status] || r.status), td(r.category),
          td(assigned, r.department ? "" : "muted"), td(formatDate(r.created_at)), td(String(r.age_days), "num"));
        return tr;
      }, null, "No pending complaints.");
    const note = document.getElementById("pending-note");
    if (note) {
      note.textContent = data.total > data.rows.length
        ? "Showing the " + data.rows.length + " oldest of " + data.total + " pending complaints."
        : data.total + " pending " + (data.total === 1 ? "complaint" : "complaints") + ", oldest first.";
    }
  }

  function loadAll() {
    show("");
    loadSummary();
    if (document.getElementById("report-status")) {
      loadStatus(); loadCategory(); loadDepartment(); loadPeriod(); loadWorkload(); loadPending();
    }
  }

  if (rangeForm) {
    rangeForm.addEventListener("submit", function (event) {
      event.preventDefault();
      const from = rangeForm.elements.from.value, to = rangeForm.elements.to.value;
      if (from && to && from > to) { show("'From' must be on or before 'To'."); return; }
      loadAll();
    });
    document.getElementById("clear-range").addEventListener("click", function () { rangeForm.reset(); loadAll(); });
  }
  const groupSelect = document.getElementById("period-group");
  if (groupSelect) groupSelect.addEventListener("change", loadPeriod);

  loadAll();
})();
