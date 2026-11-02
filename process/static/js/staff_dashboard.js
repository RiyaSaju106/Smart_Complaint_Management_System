// Staff dashboard: lists the complaints currently assigned to the signed-in staff member.
// Data comes from GET /api/staff/complaints/assigned; the server decides who sees what.
(function () {
  const rows = document.getElementById("complaint-rows");
  const filter = document.getElementById("status-filter");
  const message = document.getElementById("message");
  const count = document.getElementById("count");

  const label = (status) => status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");

  function emptyRow(text) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty";
    td.textContent = text;
    tr.appendChild(td);
    return tr;
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function render(items) {
    rows.replaceChildren();
    count.textContent = items.length + (items.length === 1 ? " complaint" : " complaints");
    if (!items.length) {
      rows.appendChild(emptyRow("No complaints are assigned to you."));
      return;
    }
    for (const c of items) {
      const tr = document.createElement("tr");
      tr.appendChild(cell(c.title));
      tr.appendChild(cell(c.category));
      tr.appendChild(cell(c.location));
      const statusTd = document.createElement("td");
      const pill = document.createElement("span");
      pill.className = "status-pill " + c.status;
      pill.textContent = label(c.status);
      statusTd.appendChild(pill);
      tr.appendChild(statusTd);
      tr.appendChild(cell(formatDate(c.created_at)));
      const actionTd = document.createElement("td");
      const link = document.createElement("a");
      link.className = "button-link";
      link.textContent = "Open";
      link.href = "/staff/complaints/" + encodeURIComponent(c.complaint_id);
      actionTd.appendChild(link);
      tr.appendChild(actionTd);
      rows.appendChild(tr);
    }
  }

  async function load() {
    scmsShow(message, "", "error");
    const query = filter.value ? "?status=" + encodeURIComponent(filter.value) : "";
    const result = await scmsApi("GET", "/api/staff/complaints/assigned" + query);
    if (result.status === 401) { window.location.href = "/login"; return; }
    if (!result.ok) {
      rows.replaceChildren(emptyRow("Could not load complaints."));
      count.textContent = "";
      scmsShow(message, scmsErrorMessage(result), "error");
      return;
    }
    render(result.data.data);
  }

  filter.addEventListener("change", load);
  load();
})();