// Staff complaint page: details, history, status transitions and remarks.
// Every write goes to the /api/staff/complaints/<id>/... endpoints. The page only offers the buttons
// the backend rules allow (passed in as data attributes); the backend still re-checks everything,
// including that this staff member is the current assignee.
(function () {
  const page = document.getElementById("complaint-page");
  const id = page.dataset.complaintId;
  const transitions = JSON.parse(page.dataset.transitions);
  const remarkable = JSON.parse(page.dataset.remarkable);
  const maxRemarks = Number(page.dataset.maxRemarks);
  const maxDetails = Number(page.dataset.maxDetails);
  const base = "/api/staff/complaints/" + encodeURIComponent(id);

  const $ = (sel) => document.getElementById(sel);
  const message = $("message");
  const label = (status) => status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");
  const BUTTON_TEXT = { in_progress: "Start work", resolved: "Mark as resolved" };

  let current = null;

  function show(text, kind) { scmsShow(message, text, kind); window.scrollTo({ top: 0, behavior: "smooth" }); }

  function renderDetail(d) {
    current = d;
    $("d-title").textContent = d.title;
    const pill = $("d-status");
    pill.textContent = label(d.status);
    pill.className = "status-pill " + d.status;
    $("d-category").textContent = d.category;
    $("d-location").textContent = d.location;
    $("d-created").textContent = formatDate(d.created_at);
    $("d-updated").textContent = formatDate(d.updated_at);
    $("d-description").textContent = d.description;
    $("detail").hidden = false;

    const res = d.resolution;
    $("d-resolution").hidden = !res;
    if (res) {
      $("d-resolution-details").textContent = res.details;
      $("d-resolution-meta").textContent = "Resolved " + formatDate(res.resolved_at);
    }

    const list = $("history");
    list.replaceChildren();
    for (const h of d.history) {
      const li = document.createElement("li");
      const what = document.createElement("div");
      const same = h.old_status === h.new_status;
      what.textContent = same
        ? "Remark (" + label(h.new_status) + ")"
        : (h.old_status ? label(h.old_status) : "New") + " → " + label(h.new_status);
      li.appendChild(what);
      if (h.remarks) {
        const note = document.createElement("div");
        note.className = "note";
        note.textContent = h.remarks;
        li.appendChild(note);
      }
      const when = document.createElement("div");
      when.className = "when";
      when.textContent = formatDate(h.changed_at);
      li.appendChild(when);
      list.appendChild(li);
    }
    $("history-panel").hidden = false;
    renderActions(d.status);
  }

  function renderActions(status) {
    const next = transitions[status] || [];
    const canRemark = remarkable.includes(status);
    $("actions").hidden = !(next.length || canRemark);
    $("status-form").hidden = !next.length;
    $("remark-form").hidden = !canRemark;
    $("details-field").hidden = !next.includes("resolved");
    $("status-help").textContent = next.length
      ? "Move this complaint to the next step."
      : "";
    
    const buttons = $("status-buttons");
    buttons.replaceChildren();
    for (const target of next) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "primary";
      b.dataset.target = target;
      b.textContent = BUTTON_TEXT[target] || "Move to " + label(target);
      buttons.appendChild(b);
    }
    if (!next.length && !canRemark) {
      show("This complaint is " + label(status).toLowerCase() + "; no further staff action is available.", "success");
    }
  }

  async function load() {
    const result = await scmsApi("GET", base);
    if (result.status === 401) { window.location.href = "/login"; return false; }
    if (!result.ok) {
      $("detail").hidden = $("actions").hidden = $("history-panel").hidden = true;
      show(scmsErrorMessage(result), "error");
      return false;
    }
    renderDetail(result.data.data);
    return true;
  }

  function setBusy(busy) {
    document.querySelectorAll("#actions button").forEach((b) => { b.disabled = busy; });
  }

  $("status-buttons").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-target]");
    if (!button) return;
    const target = button.dataset.target;
    const remarks = $("status-remarks").value.trim();
    const details = $("resolution-details").value.trim();
    if (remarks.length > maxRemarks) return show("Remarks must be at most " + maxRemarks + " characters.", "error");
    if (target === "resolved") {
      if (!details) return show("Resolution details are required to resolve a complaint.", "error");
      if (details.length > maxDetails) return show("Resolution details must be at most " + maxDetails + " characters.", "error");
    }
    if (target === "resolved" && !window.confirm("Mark this complaint as resolved? You will not be able to change it afterwards.")) return;
    const body = { status: target };
    if (remarks) body.remarks = remarks;
    if (target === "resolved") body.resolution_details = details;

    setBusy(true);
    const result = await scmsApi("PATCH", base + "/status", body);
    setBusy(false);
    if (result.status === 401) { window.location.href = "/login"; return; }
    if (!result.ok) {
      show(scmsErrorMessage(result), "error");
      if (result.status === 400 || result.status === 403) await refreshQuietly();
      return;
    }
    $("status-remarks").value = "";
    $("resolution-details").value = "";
    // Re-read from the server so what is shown is what was saved.
    if (await load()) show(result.data.message, "success");
  });

  $("remark-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("remark-text").value.trim();
    if (!text) return show("Enter a remark first.", "error");
    if (text.length > maxRemarks) return show("Remarks must be at most " + maxRemarks + " characters.", "error");
    setBusy(true);
    const result = await scmsApi("POST", base + "/remarks", { remarks: text });
    setBusy(false);
    if (result.status === 401) { window.location.href = "/login"; return; }
    if (!result.ok) { show(scmsErrorMessage(result), "error"); return; }
    $("remark-text").value = "";
    if (await load()) show(result.data.message, "success");
  });

  // After a refused change, re-read so the page does not keep offering buttons that no longer apply
  // (for example when the complaint was reassigned while the page was open). Keeps the error shown.
  async function refreshQuietly() {
    const keep = message.textContent;
    if (await load()) show(keep, "error");
  }

  load();
})();