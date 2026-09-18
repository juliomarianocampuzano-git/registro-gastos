function monthValue(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const monthInput = document.getElementById("month");
const form = document.getElementById("form");
const list = document.getElementById("list");
const summary = document.getElementById("summary");
const formError = document.getElementById("form-error");

monthInput.value = monthValue();
document.querySelector('[name="spent_on"]').value = new Date().toISOString().slice(0, 10);

async function loadAll() {
  const month = monthInput.value;
  const [expensesRes, summaryRes] = await Promise.all([
    fetch(`/api/expenses?month=${month}`),
    fetch(`/api/summary?month=${month}`),
  ]);
  const expenses = await expensesRes.json();
  const sum = await summaryRes.json();

  summary.innerHTML = `<div>Total del mes: <strong>$${Number(sum.total).toFixed(2)}</strong></div>` +
    sum.by_category.map((c) => {
      const pct = sum.total ? Math.round((c.total / sum.total) * 100) : 0;
      return `<div class="bar"><span>${c.category}</span><span>$${Number(c.total).toFixed(2)} (${pct}%)</span></div>
              <div class="fill" style="width:${pct}%"></div>`;
    }).join("");

  list.innerHTML = expenses.length
    ? expenses.map((e) => `<li>
        <div><strong>$${Number(e.amount).toFixed(2)}</strong> · ${e.category}<br/><small>${e.spent_on}${e.note ? " — " + e.note : ""}</small></div>
        <button data-id="${e.id}" class="del">Borrar</button>
      </li>`).join("")
    : "<li>No hay gastos este mes.</li>";
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  formError.hidden = true;
  const data = Object.fromEntries(new FormData(form).entries());
  const res = await fetch("/api/expenses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    formError.textContent = err.error || "No se pudo guardar";
    formError.hidden = false;
    return;
  }
  form.amount.value = "";
  form.note.value = "";
  await loadAll();
});

list.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.del");
  if (!btn) return;
  await fetch(`/api/expenses/${btn.dataset.id}`, { method: "DELETE" });
  await loadAll();
});

monthInput.addEventListener("change", loadAll);
loadAll();
