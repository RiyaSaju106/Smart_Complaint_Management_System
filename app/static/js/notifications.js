// Notification list for every role (issue #58).
// Uses the existing notification API (#28), which only ever returns the signed-in user's own rows:
//   GET   /api/notifications                  list, newest first, with unread_count
//   PATCH /api/notifications/{id}/read        mark one as read
//   PATCH /api/notifications/read-all         mark all as read
// All text is inserted with textContent.
(function () {
  const message = document.getElementById("message");
  const list = document.getElementById("notification-list");
  const summary = document.getElementById("unread-summary");
  const markAll = document.getElementById("mark-all-read");

  // Signed out (401): leave the page.
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

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function showEmpty(text) {
    list.innerHTML = "";
    list.appendChild(el("li", text, "empty"));
  }

  async function markRead(notification) {
    const result = await scmsApi("PATCH", "/api/notifications/" + notification.notification_id + "/read");
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    loadNotifications();
  }

  function notificationItem(notification) {
    const li = el("li", null, notification.is_read ? "read" : "unread");
    const body = el("div", null, "body");
    body.appendChild(el("p", notification.message, "text"));
    const meta = el("p", null, "meta");
    meta.appendChild(el("time", formatDate(notification.created_at)));
    if (notification.complaint_id) meta.appendChild(el("span", "Complaint ID: " + notification.complaint_id));
    body.appendChild(meta);
    li.appendChild(body);
    if (!notification.is_read) {
      const b = el("button", "Mark as read", "small");
      b.type = "button";
      b.addEventListener("click", () => markRead(notification));
      li.appendChild(b);
    }
    return li;
  }

  async function loadNotifications() {
    const result = await scmsApi("GET", "/api/notifications");
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { showEmpty("Could not load notifications: " + scmsErrorMessage(result)); return; }
    const { notifications, unread_count: unread } = result.data;
    summary.textContent = unread === 1 ? "1 unread notification" : unread + " unread notifications";
    markAll.hidden = unread === 0;
    if (!notifications.length) { showEmpty("You have no notifications yet."); return; }
    list.innerHTML = "";
    for (const notification of notifications) list.appendChild(notificationItem(notification));
  }

  markAll.addEventListener("click", async function () {
    markAll.disabled = true;
    const result = await scmsApi("PATCH", "/api/notifications/read-all");
    markAll.disabled = false;
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, "");
    loadNotifications();
  });

  loadNotifications();
})();
