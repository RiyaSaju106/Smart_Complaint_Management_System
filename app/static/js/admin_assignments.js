// Complaint assignment for administrators (issue #56).
// Every action goes through the existing APIs, which do the real validation and role checks:
//   GET  /api/complaints                         list and search (#27)
//   GET  /api/departments, /api/departments/{id}/staff   options (#18)
//   POST /api/complaints/{id}/assignment         assign or reassign (#19)
//   GET  /api/complaints/{id}/history            status history (#26)
// This page only shows their results and errors. All text is inserted with textContent.
(function () {
  const STATUS_LABELS = {
    submitted: "Submitted", assigned: "Assigned", in_progress: "In progress",
    resolved: "Resolved", closed: "Closed",
  };
  const UNASSIGNABLE = ["resolved", "closed"]; // the API refuses these with 409

  const message = document.getElementById("message");
  const filterForm = document.getElementById("filter-form");
  const rows = document.getElementById("complaint-rows");
  const heading = document.getElementById("list-heading");
  const prev = document.getElementById("prev-page");
  const next = document.getElementById("next-page");
  const pageInfo = document.getElementById("page-info");

  const state = { status: "submitted", q: "", page: 1 };
  let departments = null; // loaded once, on first use

  // Signed out (401) or no longer an administrator (403): leave the page.
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

  function button(label, onClick, kind) {
    const b = el("button", label, "small" + (kind ? " " + kind : ""));
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function messageRow(text) {
    rows.innerHTML = "";
    const td = el("td", text);
    td.colSpan = 6;
    const tr = el("tr");
    tr.appendChild(td);
    rows.appendChild(tr);
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function describeAssignment(assignment) {
    if (!assignment) return null;
    const dept = assignment.department.name;
    return assignment.staff ? dept + " – " + assignment.staff.name : dept + " (no staff member)";
  }

  // Removes any open assign or history panel, so only one is open at a time.
  function closeDetail() {
    const open = rows.querySelector("tr.detail");
    if (open) open.remove();
  }

  function detailRow(afterRow) {
    closeDetail();
    const tr = el("tr", null, "detail");
    const td = el("td");
    td.colSpan = 6;
    tr.appendChild(td);
    afterRow.after(tr);
    return td;
  }

  async function loadDepartments() {
    if (departments) return departments;
    const result = await scmsApi("GET", "/api/departments");
    if (leaveIfUnauthorized(result)) return null;
    if (!result.ok) { scmsShow(message, "Could not load departments: " + scmsErrorMessage(result)); return null; }
    departments = result.data.items;
    return departments;
  }

  async function fillStaff(select, departmentId) {
    select.innerHTML = "";
    select.disabled = true;
    select.appendChild(el("option", "Loading staff..."));
    const result = await scmsApi("GET", "/api/departments/" + departmentId + "/staff");
    if (leaveIfUnauthorized(result)) return;
    select.innerHTML = "";
    const none = el("option", "No staff member (department only)");
    none.value = "";
    select.appendChild(none);
    if (!result.ok) { scmsShow(message, "Could not load staff: " + scmsErrorMessage(result)); return; }
    for (const staff of result.data.items) {
      const option = el("option", staff.name);
      option.value = staff.user_id;
      select.appendChild(option);
    }
    select.disabled = false;
  }

  async function openAssign(complaint, tr) {
    scmsShow(message, "");
    const td = detailRow(tr);
    td.textContent = "Loading departments...";
    const list = await loadDepartments();
    if (!list) { closeDetail(); return; }
    td.textContent = "";
    if (!list.length) { td.textContent = "No departments exist yet."; return; }

    const form = el("div", null, "assign-form");
    const deptField = el("div");
    const deptLabel = el("label", "Department");
    const deptSelect = el("select");
    deptSelect.id = "assign-department";
    deptLabel.htmlFor = deptSelect.id;
    for (const d of list) {
      const option = el("option", d.name);
      option.value = d.department_id;
      deptSelect.appendChild(option);
    }
    const current = complaint.current_assignment;
    if (current) deptSelect.value = current.department.department_id;
    deptField.append(deptLabel, deptSelect);

    const staffField = el("div");
    const staffLabel = el("label", "Staff member");
    const staffSelect = el("select");
    staffSelect.id = "assign-staff";
    staffLabel.htmlFor = staffSelect.id;
    staffField.append(staffLabel, staffSelect);

    const confirmButton = button(current ? "Confirm reassignment" : "Confirm assignment",
      () => submitAssignment(complaint, deptSelect, staffSelect, confirmButton), "primary");
    form.append(deptField, staffField, confirmButton, button("Cancel", closeDetail));
    td.appendChild(form);

    deptSelect.addEventListener("change", () => fillStaff(staffSelect, deptSelect.value));
    await fillStaff(staffSelect, deptSelect.value);
    if (current && current.staff && current.department.department_id === deptSelect.value) {
      staffSelect.value = current.staff.user_id;
    }
    deptSelect.focus();
  }

  async function submitAssignment(complaint, deptSelect, staffSelect, confirmButton) {
    const deptName = deptSelect.options[deptSelect.selectedIndex].text;
    const staffId = staffSelect.value || null;
    const target = staffId ? deptName + " – " + staffSelect.options[staffSelect.selectedIndex].text
                           : deptName + " (no staff member)";
    const verb = complaint.current_assignment ? "Reassign" : "Assign";
    if (!window.confirm(verb + ' "' + complaint.title + '" to ' + target + "?")) return;

    confirmButton.disabled = true;
    const result = await scmsApi("POST", "/api/complaints/" + complaint.complaint_id + "/assignment",
      { department_id: deptSelect.value, staff_id: staffId });
    confirmButton.disabled = false;
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, (complaint.current_assignment ? "Reassigned" : "Assigned") + ' "' + complaint.title +
      '" to ' + target + ". Status: " + (STATUS_LABELS[result.data.status] || result.data.status) + ".", "success");
    loadComplaints();
  }

  async function openHistory(complaint, tr) {
    scmsShow(message, "");
    const td = detailRow(tr);
    td.textContent = "Loading history...";
    const result = await scmsApi("GET", "/api/complaints/" + complaint.complaint_id + "/history");
    if (leaveIfUnauthorized(result)) return;
    td.textContent = "";
    const assigned = describeAssignment(complaint.current_assignment);
    td.appendChild(el("p", "Complaint ID: " + complaint.complaint_id + " · Location: " + complaint.location +
      " · Currently assigned to: " + (assigned || "nobody")));
    if (!result.ok) { td.appendChild(el("p", "Could not load history: " + scmsErrorMessage(result))); }
    else if (!result.data.items.length) { td.appendChild(el("p", "No status changes recorded yet.", "muted")); }
    else {
      const list = el("ol", null, "history");
      for (const h of result.data.items) {
        const change = (h.old_status ? (STATUS_LABELS[h.old_status] || h.old_status) + " → " : "") +
          (STATUS_LABELS[h.new_status] || h.new_status);
        list.appendChild(el("li", formatDate(h.changed_at) + " — " + change + " by " + h.changed_by.name +
          (h.remarks ? " (" + h.remarks + ")" : "")));
      }
      td.appendChild(list);
    }
    td.appendChild(button("Close", closeDetail));
  }

  function complaintRow(complaint) {
    const tr = el("tr");
    const titleCell = el("td");
    titleCell.append(el("strong", complaint.title), el("span", complaint.complaint_id, "sub"));

    const statusCell = el("td");
    statusCell.appendChild(el("span", STATUS_LABELS[complaint.status] || complaint.status, "status-pill " + complaint.status));

    const assigned = describeAssignment(complaint.current_assignment);
    const assignedCell = el("td", assigned || "Not assigned", assigned ? "" : "muted");

    const actions = el("td", null, "actions");
    if (!UNASSIGNABLE.includes(complaint.status)) {
      actions.appendChild(button(complaint.current_assignment ? "Reassign" : "Assign",
        () => openAssign(complaint, tr), complaint.current_assignment ? "" : "primary"));
    }
    actions.appendChild(button("Details", () => openHistory(complaint, tr)));

    tr.append(titleCell, el("td", complaint.category.name), statusCell,
      el("td", formatDate(complaint.created_at)), assignedCell, actions);
    return tr;
  }

  async function loadComplaints() {
    const params = new URLSearchParams();
    if (state.status) params.set("status", state.status);
    if (state.q) params.set("q", state.q);
    params.set("page", String(state.page));
    const result = await scmsApi("GET", "/api/complaints?" + params.toString());
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) {
      messageRow("Could not load complaints: " + scmsErrorMessage(result));
      prev.disabled = next.disabled = true;
      pageInfo.textContent = "";
      return;
    }
    const { items, total, page, page_size: pageSize } = result.data;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    heading.textContent = "Complaints (" + total + ")";
    pageInfo.textContent = "Page " + page + " of " + pages;
    prev.disabled = page <= 1;
    next.disabled = page >= pages;
    if (!items.length) {
      messageRow(state.status === "submitted" && !state.q
        ? "No complaints are waiting for assignment." : "No complaints match.");
      return;
    }
    rows.innerHTML = "";
    for (const complaint of items) rows.appendChild(complaintRow(complaint));
  }

  filterForm.addEventListener("submit", function (event) {
    event.preventDefault();
    scmsShow(message, "");
    state.status = filterForm.status.value;
    state.q = filterForm.q.value.trim();
    state.page = 1;
    loadComplaints();
  });
  filterForm.status.addEventListener("change", () => filterForm.requestSubmit());
  prev.addEventListener("click", () => { state.page -= 1; loadComplaints(); });
  next.addEventListener("click", () => { state.page += 1; loadComplaints(); });

  loadComplaints();
})();
