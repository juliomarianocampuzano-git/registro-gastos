"use strict";

const el = (id) => document.getElementById(id);
const monthInput = el("month");
const form = el("form");
const list = el("list");
const pageError = el("page-error");
const formError = el("form-error");
const exportLink = el("export");
const dialog = el("delete-dialog");
const money = new Intl.NumberFormat("es-AR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
let requestController;
let pendingDelete;

function localDay(d = new Date()) {
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}

function formatMoney(cents) {
  return "$ " + money.format(cents / 100);
}

function textNode(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showError(target, message = "") {
  target.textContent = message;
  target.hidden = !message;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(
      data?.error || "No pudimos completar la operación. Volvé a intentar.",
    );
  if (data === null)
    throw new Error("La aplicación devolvió una respuesta inválida.");
  return data;
}

function renderSummary(summary) {
  el("total").textContent = formatMoney(summary.total_cents);
  el("count").textContent = String(summary.count);
  const top = summary.by_category[0];
  el("top-category").textContent = top ? top.category : "Sin gastos";
  el("top-detail").textContent = top
    ? formatMoney(top.total_cents) + " en el mes"
    : "Un buen momento para empezar";
  const container = el("categories");
  container.replaceChildren();
  if (!top) {
    container.append(
      textNode(
        "p",
        "El resumen aparece cuando registrás tu primer gasto.",
        "muted",
      ),
    );
    return;
  }
  for (const category of summary.by_category) {
    const row = textNode("div", "", "category-row");
    const heading = textNode("div", "", "category-heading");
    heading.append(
      textNode("span", category.category),
      textNode("strong", formatMoney(category.total_cents)),
    );
    const bar = document.createElement("progress");
    bar.max = summary.total_cents;
    bar.value = category.total_cents;
    bar.setAttribute(
      "aria-label",
      category.category +
        ": " +
        Math.round((category.total_cents / summary.total_cents) * 100) +
        "%",
    );
    row.append(heading, bar);
    container.append(row);
  }
}

function renderExpenses(expenses) {
  list.replaceChildren();
  el("list-caption").textContent = expenses.length
    ? "Más recientes primero · " + expenses.length + " movimientos"
    : "Tu registro empieza acá";
  if (!expenses.length) {
    const empty = textNode("li", "", "empty-state");
    empty.append(
      textNode("span", "↗", "empty-icon"),
      textNode("h3", "Todavía no hay gastos este mes"),
      textNode("p", "Cargá tu primer movimiento y empezá a ver el panorama."),
    );
    list.append(empty);
    return;
  }
  for (const expense of expenses) {
    const item = document.createElement("li");
    item.className = "expense";
    const copy = textNode("div", "", "expense-copy");
    copy.append(textNode("strong", expense.category, "expense-category"));
    const when = document.createElement("time");
    when.dateTime = expense.spent_on;
    when.textContent = expense.spent_on.split("-").reverse().join("/");
    copy.append(when);
    if (expense.note) copy.append(textNode("p", expense.note, "expense-note"));
    const actions = textNode("div", "", "expense-actions");
    const remove = textNode("button", "Eliminar", "delete-button");
    remove.type = "button";
    remove.setAttribute(
      "aria-label",
      "Eliminar gasto de " + expense.category + " del " + expense.spent_on,
    );
    remove.addEventListener("click", () => {
      pendingDelete = expense;
      el("delete-detail").textContent =
        expense.category + " · " + formatMoney(expense.amount_cents);
      dialog.showModal();
      el("cancel-delete").focus();
    });
    actions.append(
      textNode("strong", formatMoney(expense.amount_cents), "expense-amount"),
      remove,
    );
    item.append(copy, actions);
    list.append(item);
  }
}

async function loadAll() {
  requestController?.abort();
  requestController = new AbortController();
  const controller = requestController;
  const month = monthInput.value;
  showError(pageError);
  exportLink.removeAttribute("href");
  exportLink.setAttribute("aria-disabled", "true");
  if (!/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month)) {
    showError(pageError, "Elegí un mes válido para ver tus gastos.");
    return;
  }
  list.setAttribute("aria-busy", "true");
  el("stats").setAttribute("aria-busy", "true");
  try {
    const query = "?month=" + encodeURIComponent(month);
    const [expenses, summary] = await Promise.all([
      api("/api/expenses" + query, { signal: controller.signal }),
      api("/api/summary" + query, { signal: controller.signal }),
    ]);
    if (controller.signal.aborted) return;
    renderSummary(summary);
    renderExpenses(expenses);
    exportLink.href = "/api/expenses/export" + query;
    exportLink.setAttribute("aria-disabled", "false");
  } catch (error) {
    if (error.name !== "AbortError") {
      showError(
        pageError,
        error.message || "No pudimos cargar tus gastos. Revisá la conexión.",
      );
      list.replaceChildren(
        textNode("li", "No se pudieron cargar los movimientos.", "empty-state"),
      );
      el("total").textContent = "—";
      el("count").textContent = "—";
      el("top-category").textContent = "—";
      el("top-detail").textContent = "Sin conexión con los datos";
      el("categories").replaceChildren(
        textNode("p", "No se pudo cargar el resumen.", "muted"),
      );
      el("list-caption").textContent =
        "Cambiar de mes permite volver a intentar";
    }
  } finally {
    if (requestController === controller) {
      list.setAttribute("aria-busy", "false");
      el("stats").setAttribute("aria-busy", "false");
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError(formError);
  const button = el("save");
  button.disabled = true;
  const data = Object.fromEntries(new FormData(form));
  try {
    await api("/api/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    monthInput.value = data.spent_on.slice(0, 7);
    form.elements.amount.value = "";
    form.elements.note.value = "";
    el("status").textContent = "Gasto guardado.";
    await loadAll();
    el("amount").focus();
  } catch (error) {
    showError(formError, error.message || "No pudimos guardar el gasto.");
  } finally {
    button.disabled = false;
  }
});

el("cancel-delete").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  pendingDelete = null;
});
el("confirm-delete").addEventListener("click", async () => {
  if (!pendingDelete) return;
  const button = el("confirm-delete");
  button.disabled = true;
  try {
    await api("/api/expenses/" + pendingDelete.id, { method: "DELETE" });
    dialog.close();
    el("status").textContent = "Gasto eliminado.";
    await loadAll();
  } catch (error) {
    dialog.close();
    showError(pageError, error.message || "No pudimos eliminar el gasto.");
  } finally {
    button.disabled = false;
  }
});

monthInput.value = localDay().slice(0, 7);
el("spent-on").value = localDay();
monthInput.addEventListener("change", loadAll);
loadAll();
