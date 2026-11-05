// User and staff management for administrators (issue #62).
// Every action goes through the /api/admin/users endpoints (#33), which do the real validation,
// role checks and rules (e.g. staff with open complaints cannot be deactivated); this page only
// shows their results and errors.
(function () {
  const ROLE_LABELS = { resident: "Resident", maintenance_staff: "Maintenance staff" };
  const PAGE_SIZE = 20;

  const message = document.getElementById("message");
  const createForm = document.getElementById("create-form");
  const filterForm = document.getElementById("filter-form");
  const rows = document.getElementById("user-rows");
  const heading = document.getElementById("list-heading");
  const prev = document.getElementById("prev-page");
  const next = document.getElementById("next-page");
  const pageInfo = document.getElementById("page-info");
  const state = { page: 1, filters: {} };
  let departments = [];

  // Signed out (401) or no longer an administrator (403 from the role check): leave the page.
  // A 403 for one account (an administrator id) carries FORBIDDEN too, but this page never
  // lists administrators, so it cannot reach that case from a button.
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

  function input(value, maxLength, label) {
    const i = el("input");
    i.value = value || "";
    i.maxLength = maxLength;
    i.setAttribute("aria-label", label);
    return i;
  }

  function departmentSelect(selected, label, blank) {
    const select = el("select");
    select.setAttribute("aria-label", label);
    if (blank) {
      const none = el("option", blank);
      none.value = "";
      select.appendChild(none);
    }
    for (const d of departments) {
      const option = el("option", d.name);
      option.value = d.department_id;
      select.appendChild(option);
    }
    select.value = selected || "";
    return select;
  }

  function messageRow(text) {
    rows.innerHTML = "";
    const td = el("td", text);
    td.colSpan = 6;
    const tr = el("tr");
    tr.appendChild(td);
    rows.appendChild(tr);
  }

  function nameCell(user) {
    const td = el("td");
    td.append(el("strong", user.name), el("span", user.email, "sub"));
    return td;
  }

  function placeText(user) {
    return user.role === "maintenance_staff" ? (user.department || "—") : (user.unit_address || "—");
  }

  function statusCell(user) {
    const td = el("td");
    td.appendChild(el("span", user.is_active ? "Active" : "Inactive", "account-pill " + (user.is_active ? "active" : "inactive")));
    return td;
  }

  async function setActive(user, active) {
    const verb = active ? "Activate" : "Deactivate";
    const note = active ? "" : " They will not be able to sign in until the account is activated again.";
    if (!window.confirm(verb + " the account for " + user.name + " (" + user.email + ")?" + note)) return;
    const result = await scmsApi("POST", "/api/admin/users/" + user.user_id + (active ? "/activate" : "/deactivate"));
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, (active ? "Activated " : "Deactivated ") + user.name + ".", "success");
    loadUsers();
  }

  // PATCH accepts only the fields that change, and rejects empty ones, so send just the edits.
  async function saveUser(user, fields) {
    const changes = {};
    for (const [key, value] of Object.entries(fields)) {
      if (value !== (user[key] || "")) changes[key] = value;
    }
    if (!Object.keys(changes).length) { scmsShow(message, "No changes to save.", "success"); loadUsers(); return; }
    const result = await scmsApi("PATCH", "/api/admin/users/" + user.user_id, changes);
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, "Saved " + result.data.name + ".", "success");
    loadUsers();
  }

  function editRow(tr, user) {
    scmsShow(message, "");
    tr.innerHTML = "";
    const name = input(user.name, 100, "Full name");
    const contact = input(user.contact_number, 15, "Contact number");
    const isStaff = user.role === "maintenance_staff";
    const place = isStaff
      ? departmentSelect(user.department_id, "Department")
      : input(user.unit_address, 150, "Unit address");

    const nameTd = el("td");
    nameTd.append(name, el("span", user.email + " (email cannot be changed)", "sub"));
    const placeTd = el("td");
    placeTd.appendChild(place);
    const contactTd = el("td");
    contactTd.appendChild(contact);
    const actions = el("td", null, "actions");
    actions.append(
      button("Save", () => {
        const fields = { name: name.value.trim(), contact_number: contact.value.trim() };
        fields[isStaff ? "department_id" : "unit_address"] = isStaff ? place.value : place.value.trim();
        saveUser(user, fields);
      }, "primary"),
      button("Cancel", () => { scmsShow(message, ""); loadUsers(); }),
    );
    tr.append(nameTd, el("td", ROLE_LABELS[user.role]), placeTd, contactTd, statusCell(user), actions);
    name.focus();
  }

  function userRow(user) {
    const tr = el("tr");
    if (!user.is_active) tr.className = "inactive";
    const actions = el("td", null, "actions");
    actions.append(
      button("Edit", () => editRow(tr, user)),
      user.is_active
        ? button("Deactivate", () => setActive(user, false), "danger")
        : button("Activate", () => setActive(user, true)),
    );
    tr.append(nameCell(user), el("td", ROLE_LABELS[user.role] || user.role), el("td", placeText(user)),
      el("td", user.contact_number || "—"), statusCell(user), actions);
    return tr;
  }

  async function loadUsers() {
    const params = new URLSearchParams({ page: state.page, page_size: PAGE_SIZE });
    for (const [key, value] of Object.entries(state.filters)) if (value) params.set(key, value);
    const result = await scmsApi("GET", "/api/admin/users?" + params.toString());
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) {
      messageRow("Could not load accounts: " + scmsErrorMessage(result));
      prev.disabled = next.disabled = true;
      pageInfo.textContent = "";
      return;
    }
    const { items, total } = result.data;
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    heading.textContent = "Accounts (" + total + ")";
    pageInfo.textContent = "Page " + state.page + " of " + pages;
    prev.disabled = state.page <= 1;
    next.disabled = state.page >= pages;
    if (!items.length) { messageRow("No accounts match these filters."); return; }
    rows.innerHTML = "";
    for (const user of items) rows.appendChild(userRow(user));
  }

  async function loadDepartments() {
    const result = await scmsApi("GET", "/api/departments");
    if (leaveIfUnauthorized(result)) return;
    const create = createForm.department_id;
    if (!result.ok) {
      create.innerHTML = "";
      create.appendChild(el("option", "Could not load departments"));
      return;
    }
    departments = result.data.items;
    create.replaceWith(Object.assign(departmentSelect("", "Department", "Choose a department"),
      { id: "new-department", name: "department_id" }));
    const filter = filterForm.department_id;
    for (const d of departments) {
      const option = el("option", d.name);
      option.value = d.department_id;
      filter.appendChild(option);
    }
  }

  // Residents need a unit address; staff need a department and their contact number is optional.
  function showRoleFields() {
    const staff = createForm.role.value === "maintenance_staff";
    for (const node of createForm.querySelectorAll("[data-staff-only]")) node.hidden = !staff;
    for (const node of createForm.querySelectorAll("[data-resident-only]")) node.hidden = staff;
  }

  createForm.role.addEventListener("change", showRoleFields);

  createForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const role = createForm.role.value;
    const body = {
      role,
      name: createForm.name.value.trim(),
      email: createForm.email.value.trim(),
      password: createForm.password.value,
    };
    const contact = createForm.contact_number.value.trim();
    if (contact) body.contact_number = contact;
    if (role === "resident") body.unit_address = createForm.unit_address.value.trim();
    else body.department_id = createForm.department_id.value;

    // Quick checks for the common mistakes; the API validates everything again.
    if (!body.name || !body.email || !body.password) {
      scmsShow(message, "Please fill in the name, email and temporary password."); return;
    }
    if (body.password.length < 8) { scmsShow(message, "The temporary password must be at least 8 characters."); return; }
    if (role === "resident" && (!contact || !body.unit_address)) {
      scmsShow(message, "Residents need a contact number and a unit address."); return;
    }
    if (role === "maintenance_staff" && !body.department_id) {
      scmsShow(message, "Please choose a department for the staff member."); return;
    }

    const submit = document.getElementById("create-submit");
    submit.disabled = true;
    const result = await scmsApi("POST", "/api/admin/users", body);
    submit.disabled = false;
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    createForm.reset();
    showRoleFields();
    scmsShow(message, "Created " + ROLE_LABELS[result.data.role].toLowerCase() + " account for " +
      result.data.name + " (" + result.data.email + ").", "success");
    state.page = 1;
    loadUsers();
  });

  filterForm.addEventListener("submit", function (event) {
    event.preventDefault();
    scmsShow(message, "");
    state.filters = {
      role: filterForm.role.value,
      status: filterForm.status.value,
      department_id: filterForm.department_id.value,
      q: filterForm.q.value.trim(),
    };
    state.page = 1;
    loadUsers();
  });
  for (const name of ["role", "status", "department_id"]) {
    filterForm[name].addEventListener("change", () => filterForm.requestSubmit());
  }
  prev.addEventListener("click", () => { state.page -= 1; loadUsers(); });
  next.addEventListener("click", () => { state.page += 1; loadUsers(); });

  showRoleFields();
  loadDepartments().then(loadUsers);
})();
