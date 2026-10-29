(function () {
  const form = document.getElementById("login-form");
  const message = document.getElementById("message");
  const button = document.getElementById("submit");

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!email || !password) {
      scmsShow(message, "Enter your email and password.");
      return;
    }
    button.disabled = true;
    const result = await scmsApi("POST", "/api/auth/login", { email, password });
    if (result.ok) {
      window.location.href = "/home"; // /home redirects by role (resident / staff / admin)
      return;
    }
    scmsShow(message, scmsErrorMessage(result));
    button.disabled = false;
  });
})();