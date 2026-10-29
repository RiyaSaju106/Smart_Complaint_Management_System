// Shared helpers for every SCMS page. Page-specific code lives in its own file.
// Usage: const { ok, status, data } = await scmsApi("POST", "/api/auth/login", { email, password });
(function () {
  async function scmsApi(method, url, body, extraHeaders) {
    const options = { method, credentials: "same-origin", headers: { ...(extraHeaders || {}) } };
    if (body instanceof FormData) {
      options.body = body; // browser sets the multipart boundary itself
    } else if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(url, options);
    } catch (networkError) {
      return { ok: false, status: 0, data: { error: { code: "NETWORK", message: "Cannot reach the server. Please try again." } } };
    }
    let data = null;
    try { data = await response.json(); } catch (_) { /* empty or non-JSON body */ }
    return { ok: response.ok, status: response.status, data };
  }

  // Turns an API error body into one readable sentence.
  function scmsErrorMessage(result) {
    const err = result && result.data && result.data.error;
    if (!err) return "Something went wrong. Please try again.";
    return err.message || "Something went wrong. Please try again.";
  }

  function scmsShow(el, message, kind) {
    el.textContent = message;
    el.className = "msg " + (kind || "error");
    el.hidden = !message;
  }

  document.addEventListener("click", async function (event) {
    const link = event.target.closest("[data-logout]");
    if (!link) return;
    event.preventDefault();
    await scmsApi("POST", "/api/auth/logout");
    window.location.href = "/login";
  });

    // Show / hide password buttons (data-toggle-password) used on the login and register pages.
  document.addEventListener("click", function (event) {
    const toggle = event.target.closest("[data-toggle-password]");
    if (!toggle) return;
    const input = toggle.parentElement.querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });

  window.scmsApi = scmsApi;
  window.scmsErrorMessage = scmsErrorMessage;
  window.scmsShow = scmsShow;
})();