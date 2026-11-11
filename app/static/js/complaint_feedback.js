// Resident feedback form for one complaint (issue #61).
// Uses the existing APIs, which do the real eligibility, ownership and duplicate checks:
//   GET  /api/complaints?q={id}              title and status; only returns the resident's own (#27)
//   GET  /api/complaints/{id}/feedback       feedback already given, or null (#32)
//   POST /api/complaints/{id}/feedback       submit a rating and optional comment (#32)
// All text is inserted with textContent.
(function () {
  const STATUS_LABELS = {
    submitted: "Submitted", assigned: "Assigned", in_progress: "In progress",
    resolved: "Resolved", closed: "Closed",
  };
  const ELIGIBLE = ["resolved", "closed"];

  const card = document.getElementById("feedback-card");
  const complaintId = card.dataset.complaintId;
  const feedbackUrl = "/api/complaints/" + encodeURIComponent(complaintId) + "/feedback";

  const message = document.getElementById("message");
  const loading = document.getElementById("loading");
  const summary = document.getElementById("complaint-summary");
  const form = document.getElementById("feedback-form");
  const submitted = document.getElementById("submitted-view");
  const button = document.getElementById("submit");
  const ratingText = document.getElementById("rating-text");
  const counter = document.getElementById("comment-count");

  function leaveIfSignedOut(result) {
    if (result.status === 401) { window.location.href = "/login"; return true; }
    return false;
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function showSubmitted(feedback) {
    form.hidden = true;
    submitted.hidden = false;
    const stars = document.getElementById("submitted-stars");
    stars.textContent = "★".repeat(feedback.rating) + "☆".repeat(5 - feedback.rating);
    stars.setAttribute("aria-label", feedback.rating + " out of 5");
    document.getElementById("submitted-comment").textContent = feedback.comment || "";
    document.getElementById("submitted-at").textContent = formatDate(feedback.created_at);
  }

  async function load() {
    const search = await scmsApi("GET", "/api/complaints?q=" + encodeURIComponent(complaintId));
    if (leaveIfSignedOut(search)) return;
    loading.hidden = true;
    if (!search.ok) { scmsShow(message, scmsErrorMessage(search)); return; }
    const complaint = search.data.items.find((c) => c.complaint_id === complaintId);
    if (!complaint) { scmsShow(message, "We could not find this complaint on your account."); return; }

    summary.hidden = false;
    document.getElementById("complaint-title").textContent = complaint.title;
    document.getElementById("complaint-id").textContent = complaint.complaint_id;
    document.getElementById("complaint-status").textContent = STATUS_LABELS[complaint.status] || complaint.status;
    if (!ELIGIBLE.includes(complaint.status)) {
      scmsShow(message, "You can give feedback once this complaint has been resolved.", "info");
      return;
    }

    const result = await scmsApi("GET", feedbackUrl);
    if (leaveIfSignedOut(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    if (result.data.data) showSubmitted(result.data.data);
    else form.hidden = false;
  }

  form.addEventListener("change", function (event) {
    if (event.target.name !== "rating") return;
    ratingText.textContent = event.target.value + " out of 5";
    scmsShow(message, ""); // clear a "please choose a rating" error
  });

  form.comment.addEventListener("input", () => { counter.textContent = form.comment.value.length; });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const chosen = form.querySelector('input[name="rating"]:checked');
    if (!chosen) { scmsShow(message, "Please choose a rating from 1 to 5."); return; }

    button.disabled = true;
    const result = await scmsApi("POST", feedbackUrl, {
      rating: Number(chosen.value),
      comment: form.comment.value.trim() || null,
    });
    button.disabled = false;
    if (leaveIfSignedOut(result)) return;
    if (!result.ok) {
      scmsShow(message, scmsErrorMessage(result));
      // Already submitted elsewhere, or no longer eligible: show the page's true state.
      if (result.status === 409) {
        const current = await scmsApi("GET", feedbackUrl);
        if (current.ok && current.data.data) showSubmitted(current.data.data);
      }
      return;
    }
    scmsShow(message, result.data.message, "success");
    showSubmitted(result.data.data);
  });

  load();
})();
