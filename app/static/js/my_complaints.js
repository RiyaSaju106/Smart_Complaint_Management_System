// Resident complaint tracking, history and search (issue #59).
// Everything comes from the real APIs, which only ever return the signed-in resident's complaints:
//   GET /api/complaints                    search and filters (#27), role-scoped
//   GET /api/categories                    filter options (#18)
//   GET /api/complaints/{id}/status        current status and last update (#26)
//   GET /api/complaints/{id}/history       status history, oldest first (#26)
// Responses are read through scmsTracking (tracking.js). All text is inserted with textContent.
(function () {
  const T = window.scmsTracking;
  const root = document.getElementById("my-complaints");
  const myId = root.dataset.userId;
  const message = document.getElementById("message");
  const form = document.getElementById("filter-form");
  const rows = document.getElementById("complaint-rows");
  const heading = document.getElementById("list-heading");
  const prev = document.getElementById("prev-page");
  const next = document.getElementById("next-page");
  const pageInfo = document.getElementById("page-info");
  const categorySelect = document.getElementById("filter-category");

  let page = 1;

  function leaveIfUnauthorized(result) {
    if (result.status === 401) { window.location.href = "/login"; return true; }
    return false;
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function button(label, onClick, kind) {
    const b = el("button", label, "small" + (kind ? " " + kind : ""));
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function messageRow(text) {
    rows.innerHTML = "";
    const td = el("td", text);
    td.colSpan = 5;
    const tr = el("tr");
    tr.appendChild(td);
    rows.appendChild(tr);
  }

  // Only an ID may come back for the person who made a change: name the resident themself.
  function actorLabel(userId) {
    return userId === myId ? "You" : "SCMS staff";
  }

  function statusPill(status) {
    return el("span", T.statusLabel(status), "status-pill " + (status || ""));
  }

  function closeDetail() {
    const open = rows.querySelector("tr.detail");
    if (open) {
      const opener = open.previousElementSibling && open.previousElementSibling.querySelector("[aria-expanded]");
      if (opener) opener.setAttribute("aria-expanded", "false");
      open.remove();
    }
  }

  async function openDetail(complaint, tr, opener) {
    const wasOpen = tr.nextElementSibling && tr.nextElementSibling.classList.contains("detail");
    closeDetail();
    if (wasOpen) return; // second click closes it
    opener.setAttribute("aria-expanded", "true");
    const detail = el("tr", null, "detail");
    const td = el("td");
    td.colSpan = 5;
    td.textContent = "Loading status and history...";
    detail.appendChild(td);
    tr.after(detail);

    const id = encodeURIComponent(complaint.complaint_id);
    const [statusResult, historyResult] = await Promise.all([
      scmsApi("GET", "/api/complaints/" + id + "/status"),
      scmsApi("GET", "/api/complaints/" + id + "/history"),
    ]);
    if (leaveIfUnauthorized(statusResult) || leaveIfUnauthorized(historyResult)) return;
    td.textContent = "";

    const grid = el("div", null, "detail-grid");
    function fact(label, value) {
      const box = el("div");
      box.append(el("strong", label), value instanceof Node ? value : el("span", value));
      grid.appendChild(box);
    }
    fact("Complaint ID", complaint.complaint_id);
    fact("Location", complaint.location || "—");
    if (statusResult.ok) {
      const status = T.readStatus(statusResult.data);
      fact("Current status", statusPill(status.status));
      fact("Last updated", formatDate(status.updated_at));
    } else {
      fact("Current status", "Could not load: " + scmsErrorMessage(statusResult));
    }
    td.appendChild(grid);

    td.appendChild(el("h3", "History", "detail-heading"));
    if (!historyResult.ok) {
      td.appendChild(el("p", "Could not load the history: " + scmsErrorMessage(historyResult)));
    } else {
      const history = T.readHistory(historyResult.data, actorLabel);
      if (!history.length) {
        td.appendChild(el("p", "No status changes have been recorded yet.", "muted"));
      } else {
        const list = el("ol", null, "timeline");
        for (const h of history) {
          const item = el("li");
          const change = (h.old_status ? T.statusLabel(h.old_status) + " → " : "") + T.statusLabel(h.new_status);
          item.append(el("span", formatDate(h.changed_at), "when"), el("span", change + " · by " + h.actor));
          if (h.remarks) item.appendChild(el("span", "“" + h.remarks + "”", "remarks"));
          list.appendChild(item);
        }
        td.appendChild(list);
      }
    }
    td.appendChild(button("Close", closeDetail));
  }

  function complaintRow(complaint) {
    const tr = el("tr");
    const titleCell = el("td");
    titleCell.append(el("strong", complaint.title), el("span", complaint.complaint_id, "sub"));
    const statusCell = el("td");
    statusCell.appendChild(statusPill(complaint.status));
    const actions = el("td", null, "actions");
    const view = button("View", () => openDetail(complaint, tr, view), "primary");
    view.setAttribute("aria-expanded", "false");
    actions.appendChild(view);
    // Feedback opens once staff have resolved the complaint (#61); the feedback page and API re-check this.
    if (complaint.status === "resolved" || complaint.status === "closed") {
      actions.appendChild(button("Give feedback", () => {
        window.location.href = "/complaints/" + encodeURIComponent(complaint.complaint_id) + "/feedback";
      }));
    }
    tr.append(titleCell, el("td", complaint.category.name), statusCell,
      el("td", formatDate(complaint.created_at)), actions);
    return tr;
  }

  function filters() {
    const params = new URLSearchParams();
    for (const name of ["q", "status", "category_id", "from", "to"]) {
      const value = (form.elements[name].value || "").trim();
      if (value) params.set(name, value);
    }
    return params;
  }

  async function loadComplaints() {
    messageRow("Loading your complaints...");
    const params = filters();
    params.set("page", String(page));
    const result = await scmsApi("GET", "/api/complaints?" + params.toString());
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) {
      // 400 INVALID_FILTER explains which filter is wrong.
      messageRow("Could not load your complaints: " + scmsErrorMessage(result));
      heading.textContent = "Complaints";
      pageInfo.textContent = "";
      prev.disabled = next.disabled = true;
      return;
    }
    const { items, total, page: current, page_size: pageSize } = result.data;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    heading.textContent = "Complaints (" + total + ")";
    pageInfo.textContent = "Page " + current + " of " + pages;
    prev.disabled = current <= 1;
    next.disabled = current >= pages;
    if (!items.length) {
      messageRow(filters().toString() === "" && current === 1
        ? "You have not submitted any complaints yet."
        : "No complaints match your search.");
      return;
    }
    rows.innerHTML = "";
    for (const complaint of items) rows.appendChild(complaintRow(complaint));
    // Searching an exact Complaint ID opens it straight away.
    if (items.length === 1 && params.get("q") === items[0].complaint_id) {
      const first = rows.querySelector("tr");
      openDetail(items[0], first, first.querySelector("button"));
    }
  }

  async function loadCategories() {
    const result = await scmsApi("GET", "/api/categories");
    if (leaveIfUnauthorized(result) || !result.ok) return; // the filter is optional
    for (const category of result.data.items) {
      const option = el("option", category.name);
      option.value = category.category_id;
      categorySelect.appendChild(option);
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const from = form.elements.from.value, to = form.elements.to.value;
    if (from && to && from > to) { scmsShow(message, "'From' must be on or before 'To'."); return; }
    page = 1;
    loadComplaints();
  });
  document.getElementById("clear-filters").addEventListener("click", function () {
    form.reset();
    scmsShow(message, "");
    page = 1;
    loadComplaints();
  });
  prev.addEventListener("click", () => { page -= 1; loadComplaints(); });
  next.addEventListener("click", () => { page += 1; loadComplaints(); });

  // /complaints?q=<Complaint ID> (e.g. from the "Track Complaint" card) pre-fills the search.
  const initialQ = new URLSearchParams(window.location.search).get("q");
  if (initialQ) form.elements.q.value = initialQ;
  if (window.location.hash === "#search") form.elements.q.focus();

  loadCategories();
  loadComplaints();
})();
