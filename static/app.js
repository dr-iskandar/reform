let generatedRecords = [];
let masterRecords = [];
let generatedFilename = "vlm_generated.xlsx";
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
  let payload;
  try { payload = await res.json(); } catch (_) { payload = null; }
  if (!res.ok) {
    throw new Error(payload?.detail || payload?.message || ("HTTP " + res.status));
  }
  return payload;
}

async function downloadJsonAsFile(url, payload, filename) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    let message = await res.text();
    try { message = JSON.parse(message).detail || message; } catch (_) {}
    throw new Error(message);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}

function refreshIndexSuggestions() {
  const node = el("indexSuggestions");
  node.innerHTML = "";
  const fields = new Set();

  generatedRecords.slice(0, 20).forEach(row => {
    Object.keys(row).filter(k => k !== "_page").forEach(k => fields.add(k));
  });
  masterRecords.slice(0, 20).forEach(row => {
    Object.keys(row).filter(k => k !== "_page").forEach(k => fields.add(k));
  });

  [...fields].sort().forEach(field => {
    const option = document.createElement("option");
    option.value = field;
    node.appendChild(option);
  });
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

el("extractSource").addEventListener("click", async () => {
  const file = el("sourceFile").files[0];
  if (!file) return alert("Pilih softfile sumber dulu.");

  const button = el("extractSource");
  setBusy(button, true, "VLM sedang membaca…");

  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("schema_hint", el("schemaHint").value);

    const data = await apiJson("/api/extract", { method: "POST", body: fd });
    generatedRecords = data.records || [];
    generatedFilename = file.name.replace(/\.[^.]+$/, "") + "_generated.xlsx";

    el("sourceMeta").textContent =
      data.pages_processed + " page • " +
      generatedRecords.length + " row • " +
      data.model;

    el("sourcePreview").textContent = pretty(generatedRecords.slice(0, 30));
    el("downloadGenerated").disabled = generatedRecords.length === 0;
    refreshIndexSuggestions();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

el("downloadGenerated").addEventListener("click", async () => {
  if (!generatedRecords.length) return;
  try {
    await downloadJsonAsFile(
      "/api/export-generated",
      { records: generatedRecords, filename: generatedFilename },
      generatedFilename
    );
  } catch (err) {
    alert(err.message);
  }
});

el("loadMaster").addEventListener("click", async () => {
  const file = el("masterFile").files[0];
  if (!file) return alert("Pilih master Excel/CSV dulu.");

  const button = el("loadMaster");
  setBusy(button, true, "Loading master…");

  try {
    const fd = new FormData();
    fd.append("file", file);
    const data = await apiJson("/api/read-table", { method: "POST", body: fd });

    masterRecords = data.records || [];
    el("masterMeta").textContent =
      masterRecords.length + " row • columns: " + (data.columns || []).join(", ");
    el("masterPreview").textContent = pretty(masterRecords.slice(0, 20));
    refreshIndexSuggestions();
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

el("compare").addEventListener("click", async () => {
  if (!generatedRecords.length) return alert("Generate data dari softfile dulu.");
  if (!masterRecords.length) return alert("Load master data dulu.");

  const indexField = el("indexField").value.trim();
  if (!indexField) return alert("Tentukan index field.");

  const button = el("compare");
  setBusy(button, true, "Elastic comparing…");

  try {
    lastComparison = await apiJson("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_records: generatedRecords,
        master_records: masterRecords,
        index_field: indexField
      })
    });

    renderComparison(lastComparison);
    el("exportComparison").disabled = !(lastComparison.rows || []).length;
  } catch (err) {
    alert(err.message);
  } finally {
    setBusy(button, false);
  }
});

function renderComparison(data) {
  const warningNode = el("warnings");
  const warnings = data.warnings || [];
  warningNode.textContent = warnings.join(" • ");

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

  const details = data.details || [];
  if (!details.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.textContent = "Belum ada detail perbandingan.";
    td.className = "empty-state";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  details.forEach((r) => {
    const tr = document.createElement("tr");
    if (r.is_index) tr.classList.add("index-row");

    const score = Math.round((Number(r.value_match_score) || 0) * 100) + "%";
    const values = [
      r.source_row ?? "-",
      r.generated_field ?? "",
      r.generated_value ?? "",
      r.master_field ?? "",
      r.master_value ?? "",
    ];

    values.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = String(v);
      tr.appendChild(td);
    });

    const statusTd = document.createElement("td");
    const badge = document.createElement("span");
    const status = r.status || "";
    const className =
      status === "SAME" ? "match" :
      status === "DIFFERENT" ? "mismatch" :
      status === "NOT_FOUND" ? "near_match" : "missing";
    badge.className = "badge " + className;
    badge.textContent = status;
    statusTd.appendChild(badge);
    tr.appendChild(statusTd);

    const modeTd = document.createElement("td");
    modeTd.textContent = r.comparison_mode || r.record_match_mode || "";
    tr.appendChild(modeTd);

    const scoreTd = document.createElement("td");
    scoreTd.textContent = score;
    tr.appendChild(scoreTd);

    tbody.appendChild(tr);
  });
}

el("exportComparison").addEventListener("click", async () => {
  if (!lastComparison) return;
  try {
    await downloadJsonAsFile(
      "/api/export-comparison",
      {
        summary: lastComparison.summary,
        rows: lastComparison.rows,
        details: lastComparison.details
      },
      "reform_comparison_result.xlsx"
    );
  } catch (err) {
    alert(err.message);
  }
});

health();
