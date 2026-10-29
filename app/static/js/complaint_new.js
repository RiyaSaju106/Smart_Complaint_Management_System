(function () {
  const MAX_BYTES = 5 * 1024 * 1024; // matches ATTACHMENT_MAX_BYTES on the server
  const ALLOWED = ["pdf", "png", "jpg", "jpeg"];

  const form = document.getElementById("complaint-form");
  const message = document.getElementById("message");
  const button = document.getElementById("submit");
  const select = document.getElementById("category");
  const counter = document.getElementById("desc-count");

  // One key per form fill. If the request fails and the resident presses Submit again, the same
  // key is sent, so the server returns the existing complaint instead of creating a duplicate
  // (NFR-002 / NFR-004).
  function newKey() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "k-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }
  let idempotencyKey = newKey();

  form.description.addEventListener("input", () => { counter.textContent = form.description.value.length; });

  async function loadCategories() {
    const result = await scmsApi("GET", "/api/categories");
    if (result.status === 401) { window.location.href = "/login"; return; }
    if (!result.ok) {
      select.innerHTML = '<option value="">Could not load categories</option>';
      scmsShow(message, scmsErrorMessage(result));
      return;
    }
    select.innerHTML = '<option value="">Select a category</option>';
    for (const c of result.data.items) {
      const option = document.createElement("option");
      option.value = c.category_id;
      option.textContent = c.name;
      select.appendChild(option);
    }
  }

  function checkFile(file) {
    if (!file) return "";
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED.includes(ext)) return "Attachment must be a PDF, PNG or JPG file.";
    if (file.size > MAX_BYTES) return "Attachment must be 5 MB or smaller.";
    return "";
  }

  function showSuccess(data, attachmentNote) {
    document.getElementById("form-view").hidden = true;
    document.getElementById("success-view").hidden = false;
    document.getElementById("complaint-id").textContent = data.complaint_id;
    document.getElementById("complaint-status").textContent = data.status;
    const note = document.getElementById("success-message");
    note.textContent = "Your complaint has been registered." + (attachmentNote ? " " + attachmentNote : "");
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");

    const body = {
      title: form.title.value.trim(),
      category_id: form.category_id.value,
      description: form.description.value.trim(),
      location: form.location.value.trim(),
    };
    if (!body.title || !body.category_id || !body.description || !body.location) {
      scmsShow(message, "Please fill in the title, category, description and location.");
      return;
    }
    const file = form.file.files[0];
    const fileProblem = checkFile(file);
    if (fileProblem) { scmsShow(message, fileProblem); return; }

    button.disabled = true;
    const result = await scmsApi("POST", "/api/complaints", body, { "Idempotency-Key": idempotencyKey });
    if (result.status === 401 || result.status === 403) { window.location.href = "/login"; return; }
    if (!result.ok) {
      scmsShow(message, scmsErrorMessage(result) + " You can press Submit again safely.");
      button.disabled = false;
      return; // keep the same idempotencyKey for the retry
    }

    const created = result.data.data;
    let attachmentNote = "";
    if (file) {
      const upload = new FormData();
      upload.append("file", file);
      const uploaded = await scmsApi("POST", "/api/complaints/" + created.complaint_id + "/attachments", upload);
      attachmentNote = uploaded.ok
        ? "Attachment uploaded."
        : "The complaint was saved but the attachment failed: " + scmsErrorMessage(uploaded);
    }
    idempotencyKey = newKey(); // next complaint gets a fresh key
    showSuccess(created, attachmentNote);
  });

  loadCategories();
})();