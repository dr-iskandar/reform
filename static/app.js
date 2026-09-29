let sourceRecords = [];
let targetRecords = [];
let lastComparison = null;

const el = (id) => document.getElementById(id);

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function setBusy(button, busy, text) {
  if (!button.dataset.original) button.dataset.original = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? text : button.dataset.original;
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let message = await res.text();
    try { message = JSON.parse(message).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return res.json();
}

async function health() {
  const node = el("health");
  try {
    const data = await apiJson("/api/health");
    if (data.ok) {
      node.className = "status ok";
      node.textContent = data.model_available
        ? "Ollama ready • " + data.model
        : "Ollama ready • model belum di-pull: " + data.model;
    } else {
      node.className = "status bad";
      node.textContent = "Ollama offline";
    }
  } catch (_) {
    node.className = "status bad";
    node.textContent = "Backend offline";
  }
}

async function extractFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("schema_hint", el("schemaHint").value);
  return apiJson("/api/extract", { method: "POST", body: fd });
}

el("extractSource").addEventListener("click", async () => {
  const file = el("sourceFile").files[0];
  if (!file) return alert("Pilih dokumen sumber dulu.");
  const button = el("extractSource");
  setBusy(button, true, "VLM sedang membaca…");
  try {
    const data = await extractFile(file);
    sourceRecords = data.records || [];
    el("sourceMeta").textContent =
      data.pages_processed + " page • " + sourceRecords.length + " record • " + data.model;
    el("sourcePreview").textContent = pretty(sourceRecords);
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

el("loadTarget").addEventListener("click", async () => {
  const file = el("targetFile").files[0];
  if (!file) return alert("Pilih file pembanding dulu.");
  const button = el("loadTarget");
  setBusy(button, true, "Loading…");
  try {
    const lower = file.name.toLowerCase();
    let data;
    if (lower.endsWith(".csv") || lower.endsWith(".xlsx") || lower.endsWith(".xlsm")) {
      const fd = new FormData();
      fd.append("file", file);
      data = await apiJson("/api/read-table", { method: "POST", body: fd });
      targetRecords = data.records || [];
      el("targetMeta").textContent =
        "Master data • " + targetRecords.length + " rows • " + (data.columns || []).length + " columns";
    } else {
      data = await extractFile(file);
      targetRecords = data.records || [];
      el("targetMeta").textContent =
        "Document B • " + data.pages_processed + " page • " + targetRecords.length + " record";
    }
    el("targetPreview").textContent = pretty(targetRecords.slice(0, 30));
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

el("compare").addEventListener("click", async () => {
  if (!sourceRecords.length) return alert("Extract dokumen sumber dulu.");
  if (!targetRecords.length) return alert("Load data pembanding dulu.");
  const button = el("compare");
  setBusy(button, true, "Comparing…");
  try {
    lastComparison = await apiJson("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_records: sourceRecords,
        target_records: targetRecords,
        match_key: el("matchKey").value.trim() || null
      })
    });
    renderComparison(lastComparison);
    el("export").disabled = false;
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

function renderComparison(data) {
  const summary = el("summary");
  summary.innerHTML = "";
  Object.entries(data.summary || {}).forEach(([key, value]) => {
    const span = document.createElement("span");
    span.className = "pill";
    span.textContent = key.replaceAll("_", " ") + ": " + value;
    summary.appendChild(span);
  });

  const tbody = el("results");
  tbody.innerHTML = "";
  (data.rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const values = [
      r.source_row,
      r.target_row ?? "-",
      r.field,
      r.source_value ?? "",
      r.target_value ?? "",
      Math.round((r.field_similarity || 0) * 100) + "%"
    ];
    values.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = String(v);
      tr.appendChild(td);
    });
    const td = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge " + r.status;
    badge.textContent = r.status;
    td.appendChild(badge);
    tr.appendChild(td);
    tbody.appendChild(tr);
  });
}

el("export").addEventListener("click", async () => {
  if (!lastComparison) return;
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(lastComparison)
  });
  if (!res.ok) return alert("Export gagal.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "reform_comparison.xlsx";
  a.click();
  URL.revokeObjectURL(url);
});

health();
