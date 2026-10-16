const fileInput = document.querySelector("#file");
const fileLabel = document.querySelector("#file-label");
const convertButton = document.querySelector("#convert");
const form = document.querySelector("#convert-form");
const dropTarget = document.querySelector("#drop-target");
const formError = document.querySelector("#form-error");
const result = document.querySelector("#result");
const historyList = document.querySelector("#history-list");
const historyEmpty = document.querySelector("#history-empty");
const historyError = document.querySelector("#history-error");
const preview = document.querySelector("#preview");
const raw = document.querySelector("#raw");

let selectedFile = null;
let currentId = null;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) return;
  await convertFile(selectedFile);
});

fileInput.addEventListener("change", () => {
  setFile(fileInput.files[0] || null);
});

["dragenter", "dragover"].forEach((name) => {
  dropTarget.addEventListener(name, (event) => {
    event.preventDefault();
    dropTarget.classList.add("is-hot");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropTarget.addEventListener(name, (event) => {
    event.preventDefault();
    dropTarget.classList.remove("is-hot");
  });
});

dropTarget.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});

document.querySelector("#refresh").addEventListener("click", loadHistory);
document.querySelector("#tab-preview").addEventListener("click", () => setTab("preview"));
document.querySelector("#tab-raw").addEventListener("click", () => setTab("raw"));

loadHistory();

function setFile(file) {
  selectedFile = file;
  fileLabel.textContent = file ? file.name : "Drop a PDF, Office file, HTML, data file, or image";
  convertButton.disabled = !file;
  hide(formError);
}

async function convertFile(file) {
  convertButton.disabled = true;
  convertButton.textContent = "Converting…";
  hide(formError);
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const response = await fetch("/api/convert", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) {
      show(formError, payload.detail || "The file could not be converted.");
      return;
    }
    showResult(payload);
    await loadHistory();
    fileInput.value = "";
  } catch {
    show(formError, "The converter could not be reached.");
  } finally {
    convertButton.disabled = !selectedFile;
    convertButton.textContent = "Convert";
  }
}

async function loadHistory() {
  hide(historyError);
  try {
    const response = await fetch("/api/history");
    const payload = await response.json();
    if (!response.ok) {
      historyList.replaceChildren();
      historyEmpty.hidden = true;
      show(historyError, payload.detail || "History is unavailable.");
      return;
    }
    renderHistory(payload);
  } catch {
    show(historyError, "History could not be loaded.");
  }
}

function renderHistory(rows) {
  historyList.replaceChildren();
  historyEmpty.hidden = rows.length > 0;
  rows.forEach((row) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item" + (row.id === currentId ? " is-on" : "");
    const title = document.createElement("strong");
    title.textContent = row.filename;
    const meta = document.createElement("span");
    meta.className = "history-meta";
    meta.textContent = `${savingsText(row)} · ${formatWhen(row.created_at)}`;
    button.append(title, meta);
    button.addEventListener("click", () => openHistory(row.id));
    item.append(button);
    historyList.append(item);
  });
}

async function openHistory(id) {
  hide(formError);
  const response = await fetch(`/api/history/${id}`);
  const payload = await response.json();
  if (!response.ok) {
    show(formError, payload.detail || "That conversion could not be opened.");
    return;
  }
  showResult(payload);
  await loadHistory();
}

function showResult(row) {
  currentId = row.id || null;
  result.hidden = false;
  document.querySelector("#result-name").textContent = row.filename;
  document.querySelector("#result-note").textContent = row.extension
    ? `Converted from ${row.extension}`
    : "";
  document.querySelector("#stat-source").textContent = row.source_tokens == null
    ? "None"
    : formatNumber(row.source_tokens);
  document.querySelector("#stat-markdown").textContent = formatNumber(row.markdown_tokens);
  document.querySelector("#stat-savings").textContent = row.savings_pct == null
    ? "Kept"
    : `${Number(row.savings_pct).toFixed(1)}%`;
  const warning = document.querySelector("#result-warning");
  if (row.warning) show(warning, row.warning);
  else hide(warning);
  raw.textContent = row.markdown || "";
  preview.innerHTML = renderMarkdown(row.markdown || "");
  const download = document.querySelector("#download");
  if (row.id) {
    download.href = `/api/history/${row.id}/download`;
    download.removeAttribute("download");
  } else {
    const blob = new Blob([row.markdown || ""], { type: "text/markdown" });
    download.href = URL.createObjectURL(blob);
    download.download = markdownName(row.filename);
  }
  setTab("preview");
}

function setTab(which) {
  const previewOn = which === "preview";
  preview.hidden = !previewOn;
  raw.hidden = previewOn;
  document.querySelector("#tab-preview").classList.toggle("is-on", previewOn);
  document.querySelector("#tab-preview").setAttribute("aria-selected", String(previewOn));
  document.querySelector("#tab-raw").classList.toggle("is-on", !previewOn);
  document.querySelector("#tab-raw").setAttribute("aria-selected", String(!previewOn));
}

function savingsText(row) {
  if (row.savings_pct == null) return "Context captured";
  const value = Number(row.savings_pct);
  if (value >= 0) return `${value.toFixed(1)}% fewer tokens`;
  return `${Math.abs(value).toFixed(1)}% more tokens`;
}

function formatNumber(value) {
  return Number(value).toLocaleString();
}

function formatWhen(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function markdownName(filename) {
  const stem = (filename || "document").replace(/\.[^.]+$/, "");
  return `${stem || "document"}.md`;
}

function show(node, message) {
  node.hidden = false;
  node.textContent = message;
}

function hide(node) {
  node.hidden = true;
  node.textContent = "";
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (isTableStart(lines, index)) {
      const tableLines = [];
      while (index < lines.length && lines[index].includes("|")) {
        tableLines.push(lines[index]);
        index += 1;
      }
      blocks.push(renderTable(tableLines));
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      blocks.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(`<li>${inline(lines[index].replace(/^\s*[-*]\s+/, ""))}</li>`);
        index += 1;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(`<li>${inline(lines[index].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        index += 1;
      }
      blocks.push(`<ol>${items.join("")}</ol>`);
      continue;
    }
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].startsWith("```") &&
      !lines[index].startsWith("#") &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+\.\s+/.test(lines[index]) &&
      !isTableStart(lines, index)
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
  }
  return blocks.join("");
}

function isTableStart(lines, index) {
  return lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1]);
}

function renderTable(lines) {
  const rows = lines
    .filter((line) => !/^\s*\|?\s*:?-{3,}/.test(line))
    .map((line) => splitRow(line));
  if (!rows.length) return "";
  const head = rows[0].map((cell) => `<th>${inline(cell)}</th>`).join("");
  const body = rows.slice(1).map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function splitRow(line) {
  let text = line.trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|")) text = text.slice(0, -1);
  return text.split("|").map((cell) => cell.trim());
}

function inline(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, url) => {
    const safe = safeUrl(url);
    if (!safe) return label;
    return `<a href="${escapeHtml(safe)}" rel="noreferrer">${label}</a>`;
  });
  return html;
}

function safeUrl(url) {
  const value = url.trim();
  if (/^(https?:|mailto:)/i.test(value)) return value;
  if (value.startsWith("#") && !/[\s"'<>]/.test(value)) return value;
  return "";
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
