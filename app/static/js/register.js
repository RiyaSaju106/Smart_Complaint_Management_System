(function () {
  const form = document.getElementById("register-form");
  const message = document.getElementById("message");
  const button = document.getElementById("submit");
  const fields = ["name", "email", "password", "contact_number", "unit_address"];

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const body = {};
    for (const f of fields) body[f] = form[f].value.trim();
    body.password = form.password.value; // do not trim passwords
    if (fields.some((f) => !body[f])) {
      scmsShow(message, "Please fill in every field.");
      return;
    }
    if (body.password.length < 8) {
      scmsShow(message, "Password must be at least 8 characters.");
      return;
    }
    button.disabled = true;
    const result = await scmsApi("POST", "/api/auth/register", body);
    if (result.ok) {
      scmsShow(message, "Account created. Taking you to sign in...", "success");
      setTimeout(() => { window.location.href = "/login"; }, 1200);
      return;
    }
    scmsShow(message, scmsErrorMessage(result));
    button.disabled = false;
  });
})();