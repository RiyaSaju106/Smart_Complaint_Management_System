// Reads the complaint status and history API responses (#26) for every page that shows them.
// Two response formats exist on main at the moment, so both are accepted:
//   contract (app/tracking):   {complaint_id, status, updated_at}
//                              {complaint_id, items: [{..., changed_by: {user_id, name}}]}
//   processing (process/):     {status: "success", data: {complaint_id, status, updated_at}}
//                              {status: "success", data: {complaint_id, history: [{..., changed_by: "<user_id>"}]}}
// When only an ID is given for the person who made a change, actorLabel(userId) names them.
(function () {
  const STATUS_LABELS = {
    submitted: "Submitted", assigned: "Assigned", in_progress: "In progress",
    resolved: "Resolved", closed: "Closed",
  };

  function payload(body) {
    return body && body.data && typeof body.data === "object" ? body.data : (body || {});
  }

  // -> {complaint_id, status, updated_at}
  function readStatus(body) {
    const data = payload(body);
    return { complaint_id: data.complaint_id, status: data.status, updated_at: data.updated_at };
  }

  // -> [{old_status, new_status, actor, remarks, changed_at}], oldest first
  function readHistory(body, actorLabel) {
    const data = payload(body);
    const rows = Array.isArray(data.items) ? data.items : (Array.isArray(data.history) ? data.history : []);
    return rows.map(function (h) {
      const by = h.changed_by;
      let actor;
      if (by && typeof by === "object") actor = by.name || (actorLabel ? actorLabel(by.user_id) : by.user_id);
      else actor = actorLabel ? actorLabel(by) : by;
      return { old_status: h.old_status, new_status: h.new_status, actor: actor || "Unknown",
               remarks: h.remarks, changed_at: h.changed_at };
    });
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || status || "—";
  }

  window.scmsTracking = { readStatus, readHistory, statusLabel, STATUS_LABELS };
})();
