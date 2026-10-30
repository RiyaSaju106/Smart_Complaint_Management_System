// Category and department management for administrators (issue #55).
// Every action goes through the existing /api/categories and /api/departments endpoints, which do
// the real validation and role checks; this page only shows their results and errors.
(function () {
  const message = document.getElementById("message");
  const form = document.getElementById("category-form");
  const categoryRows = document.getElementById("category-rows");
  const departmentRows = document.getElementById("department-rows");

  // Signed out (401) or no longer an administrator (403): leave the page.
  function leaveIfUnauthorized(result) {
    if (result.status === 401) { window.location.href = "/login"; return true; }
    if (result.status === 403) { window.location.href = "/home"; return true; }
    return false;
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function button(label, onClick, kind) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "small" + (kind ? " " + kind : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  function messageRow(tbody, columns, text) {
    tbody.innerHTML = "";
    const td = cell(text);
    td.colSpan = columns;
    const tr = document.createElement("tr");
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  // PUT needs every field, so edits and (de)activation both send the full category.
  async function saveCategory(category, changes, done) {
    const body = { name: category.name, description: category.description, is_active: category.is_active, ...changes };
    const result = await scmsApi("PUT", "/api/categories/" + category.category_id, body);
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, done, "success");
    loadCategories();
  }

  async function deleteCategory(category) {
    if (!window.confirm('Delete the category "' + category.name + '"? This cannot be undone.')) return;
    const result = await scmsApi("DELETE", "/api/categories/" + category.category_id);
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    scmsShow(message, 'Deleted "' + category.name + '".', "success");
    loadCategories();
  }

  function editRow(tr, category) {
    tr.innerHTML = "";
    const name = document.createElement("input");
    name.value = category.name;
    name.maxLength = 100;
    name.setAttribute("aria-label", "Category name");
    const description = document.createElement("input");
    description.value = category.description || "";
    description.maxLength = 255;
    description.setAttribute("aria-label", "Category description");
    const nameCell = document.createElement("td");
    nameCell.appendChild(name);
    const descriptionCell = document.createElement("td");
    descriptionCell.appendChild(description);
    const actions = document.createElement("td");
    actions.className = "actions";
    actions.append(
      button("Save", () => saveCategory(
        category,
        { name: name.value, description: description.value },
        'Saved "' + name.value.trim() + '".',
      ), "primary"),
      button("Cancel", () => loadCategories()),
    );
    tr.append(nameCell, descriptionCell, cell(category.is_active ? "Active" : "Inactive"), actions);
    name.focus();
  }

  function categoryRow(category) {
    const tr = document.createElement("tr");
    if (!category.is_active) tr.className = "inactive";
    const actions = document.createElement("td");
    actions.className = "actions";
    actions.append(
      button("Edit", () => editRow(tr, category)),
      category.is_active
        ? button("Deactivate", () => saveCategory(category, { is_active: false }, 'Deactivated "' + category.name + '".'))
        : button("Activate", () => saveCategory(category, { is_active: true }, 'Activated "' + category.name + '".')),
      button("Delete", () => deleteCategory(category), "danger"),
    );
    tr.append(
      cell(category.name),
      cell(category.description || "—"),
      cell(category.is_active ? "Active" : "Inactive"),
      actions,
    );
    return tr;
  }

  async function loadCategories() {
    const result = await scmsApi("GET", "/api/categories?include_inactive=true");
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { messageRow(categoryRows, 4, "Could not load categories: " + scmsErrorMessage(result)); return; }
    if (!result.data.items.length) { messageRow(categoryRows, 4, "No categories yet. Add one above."); return; }
    categoryRows.innerHTML = "";
    for (const category of result.data.items) categoryRows.appendChild(categoryRow(category));
  }

  async function showStaff(department, td) {
    td.textContent = "Loading...";
    const result = await scmsApi("GET", "/api/departments/" + department.department_id + "/staff");
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { td.textContent = "Could not load staff: " + scmsErrorMessage(result); return; }
    td.textContent = result.data.items.length
      ? result.data.items.map((s) => s.name).join(", ")
      : "No staff in this department yet.";
  }

  async function loadDepartments() {
    const result = await scmsApi("GET", "/api/departments");
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { messageRow(departmentRows, 3, "Could not load departments: " + scmsErrorMessage(result)); return; }
    if (!result.data.items.length) { messageRow(departmentRows, 3, "No departments found."); return; }
    departmentRows.innerHTML = "";
    for (const department of result.data.items) {
      const staff = document.createElement("td");
      staff.appendChild(button("View staff", () => showStaff(department, staff)));
      const tr = document.createElement("tr");
      tr.append(cell(department.name), cell(department.description || "—"), staff);
      departmentRows.appendChild(tr);
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    scmsShow(message, "");
    const body = { name: form.name.value.trim(), description: form.description.value.trim() || null };
    if (!body.name) { scmsShow(message, "Please enter a category name."); return; }
    const submit = document.getElementById("add-category");
    submit.disabled = true;
    const result = await scmsApi("POST", "/api/categories", body);
    submit.disabled = false;
    if (leaveIfUnauthorized(result)) return;
    if (!result.ok) { scmsShow(message, scmsErrorMessage(result)); return; }
    form.reset();
    scmsShow(message, 'Added "' + result.data.name + '".', "success");
    loadCategories();
  });

  loadCategories();
  loadDepartments();
})();
