const fileInputs = Array.from(document.querySelectorAll(".upload-input"));
const processButton = document.querySelector("#process-button");
const copyNotesButton = document.querySelector("#copy-notes-button");
const copyFeedback = document.querySelector("#copy-feedback");
const gradeSelects = Array.from(document.querySelectorAll("#grade-selection select"));
const processForm = document.querySelector("#process-form");
let resultIsStale = false;

function markResultStale() {
  resultIsStale = true;
  const result = document.querySelector("#generated-result");
  const download = document.querySelector(".secondary-download");
  const empty = document.querySelector("#result-empty");
  if (result) result.hidden = true;
  if (download) download.hidden = true;
  if (empty) empty.hidden = false;
  const resultSummary = document.querySelector('[data-summary-slot="result"]');
  if (resultSummary) {
    resultSummary.classList.toggle("is-loaded", false);
    resultSummary.querySelector("[data-summary-name]").textContent = "Pendiente de generar";
    resultSummary.querySelector("[data-summary-name]").removeAttribute("title");
    resultSummary.querySelector("[data-file-state]").textContent = "Pendiente";
  }
  const resultTag = document.querySelector(".results-heading .subtle-tag");
  if (resultTag) resultTag.textContent = "POR COMPLETAR";
  const resultCount = document.querySelector(".nav-count");
  if (resultCount) resultCount.hidden = true;
  const banner = document.querySelector(".status-banner");
  if (banner) {
    banner.classList.toggle("is-ready", false);
    banner.classList.toggle("is-pending", true);
  }
  const status = document.querySelector("#process-status");
  if (status) status.textContent = "La selección cambió. Carga las columnas si reemplazaste archivos y vuelve a generar el resultado.";
}

function updateFileCard(input) {
  const card = input.closest?.(".upload-card");
  if (!card) return;
  const file = input.files?.[0];
  const existingName = input.dataset.existingName || "";
  const available = Boolean(file || existingName);
  const label = card.querySelector(".file-label");
  label.querySelector("[data-file-label]").textContent = file ? file.name : label.dataset.defaultLabel;
  label.querySelector(".dropzone-caption").textContent = file ? "Archivo seleccionado" : "o arrástralo aquí";
  card.classList.toggle("has-file", available);
  card.querySelector(".loaded-file-bar").hidden = !available;
  card.querySelector("[data-loaded-name]").textContent = file ? file.name : existingName;
  const summary = document.querySelector(`[data-summary-slot="${card.dataset.fileSlot}"]`);
  if (summary) {
    const name = file ? file.name : existingName;
    summary.classList.toggle("is-loaded", available);
    summary.querySelector("[data-summary-name]").textContent = name || "Sin archivo seleccionado";
    summary.querySelector("[data-summary-name]").title = name;
    summary.querySelector("[data-file-state]").textContent = file ? "Seleccionado" : available ? "Cargado" : "Pendiente";
  }
}

function updateWorkflow(hasNewFile) {
  const counter = document.querySelector("#file-counter");
  if (counter) counter.textContent = `${fileInputs.filter(hasAvailableFile).length}/2`;
  const resultReady = processForm?.dataset.ready === "true" && !resultIsStale;
  const columnsReady = gradeSelects.length === 2 && !hasNewFile;
  const currentStep = resultReady ? 3 : columnsReady ? 2 : 1;
  [1, 2, 3].forEach((step) => {
    const element = document.querySelector(`[data-workflow-step="${step}"]`);
    if (!element) return;
    element.classList.toggle("is-current", step === currentStep);
    element.classList.toggle("is-complete", step < currentStep);
    if (step === currentStep) element.setAttribute("aria-current", "step");
    else element.removeAttribute("aria-current");
    const number = element.querySelector(".workflow-number");
    number.textContent = `0${step}`;
  });
}

function hasAvailableFile(input) {
  const hasSelectedFile = input.files && input.files.length > 0;
  const hasExistingFile = input.dataset.hasExisting === "true";
  return hasSelectedFile || hasExistingFile;
}

function updateProcessButton() {
  if (!processButton) {
    return;
  }

  const hasNewFile = fileInputs.some((input) => input.files && input.files.length > 0);
  gradeSelects.forEach((select) => { select.disabled = hasNewFile; });
  const hasSelection = gradeSelects.length === 2 && gradeSelects.every((select) => select.value !== "");
  const canProcess = fileInputs.every((input) => hasAvailableFile(input)) && (hasNewFile || hasSelection);
  processButton.textContent = hasNewFile || gradeSelects.length === 0 ? "Cargar columnas" : "Procesar y generar archivo";
  processButton.disabled = !canProcess;
  processButton.classList.toggle("is-disabled", !canProcess);
  updateWorkflow(hasNewFile);
}

function showUploadError(input, message) {
  const error = document.querySelector(`#${input.id.replace("-file", "-error")}`);
  if (error) {
    error.textContent = message;
    error.hidden = !message;
  }
  input.setAttribute?.("aria-invalid", message ? "true" : "false");
}

function fileValidationError(file) {
  if (!file) return "";
  if (!/\.(xls|xlsx|csv)$/i.test(file.name)) return "Elige un archivo .xls, .xlsx o .csv.";
  if (file.size > 16 * 1024 * 1024) return "El archivo supera el límite de 16 MiB.";
  return "";
}

fileInputs.forEach((input) => {
  input.addEventListener("change", () => {
    const error = fileValidationError(input.files?.[0]);
    showUploadError(input, error);
    if (error) {
      input.value = "";
      updateFileCard(input);
      updateProcessButton();
      return;
    }
    updateFileCard(input);
    markResultStale();
    updateProcessButton();
    const status = document.querySelector("#process-status");
    if (status) {
      const hasNewFile = fileInputs.some((fileInput) => fileInput.files?.length);
      status.textContent = !fileInputs.every(hasAvailableFile)
        ? "Selecciona ambos archivos para continuar."
        : hasNewFile ? "Archivos seleccionados. Carga sus columnas para continuar."
        : "Elige origen y destino para generar el archivo.";
    }
  });

  const dropzone = input.closest?.(".upload-control");
  if (dropzone) {
    let dragDepth = 0;
    dropzone.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      dropzone.classList.toggle("is-dragging", true);
    });
    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    });
    dropzone.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) dropzone.classList.toggle("is-dragging", false);
    });
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dragDepth = 0;
      dropzone.classList.toggle("is-dragging", false);
      const files = event.dataTransfer?.files;
      if (!files?.length) return;
      const error = files.length !== 1 ? "Carga un solo archivo en cada recuadro." : fileValidationError(files[0]);
      showUploadError(input, error);
      if (error) return;
      input.files = files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  updateFileCard(input);
});

gradeSelects.forEach((select) => {
  select.addEventListener("change", () => {
    markResultStale();
    updateProcessButton();
  });
});

if (processForm) {
  processForm.addEventListener("submit", (event) => {
    if (event.submitter && event.submitter !== processButton) return;
    const totalSize = fileInputs.reduce((total, input) => total + (input.files?.[0]?.size || 0), 0);
    if (totalSize >= 16 * 1024 * 1024) {
      event.preventDefault();
      document.querySelector("#process-status").textContent = "Los dos archivos juntos deben pesar menos de 16 MiB.";
      return;
    }
    processForm.setAttribute("aria-busy", "true");
    processButton.classList.toggle("is-loading", true);
    processButton.textContent = gradeSelects.length === 2 && !fileInputs.some((input) => input.files?.length)
      ? "Generando archivo…" : "Cargando columnas…";
    processButton.disabled = true;
  });
  window.addEventListener("pageshow", () => {
    processForm.removeAttribute("aria-busy");
    processButton.classList.toggle("is-loading", false);
    updateProcessButton();
  });
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "");
  helper.style.position = "absolute";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  helper.select();
  document.execCommand("copy");
  document.body.removeChild(helper);
}

if (copyNotesButton) {
  copyNotesButton.addEventListener("click", async () => {
    const noteCells = Array.from(document.querySelectorAll("#result-table tbody .note-cell"));
    const notes = noteCells
      .map((cell) => cell.textContent.trim())
      .filter((value) => value.length > 0);

    if (notes.length === 0) {
      if (copyFeedback) {
        copyFeedback.textContent = "No hay notas para copiar.";
      }
      return;
    }

    try {
      await copyText(notes.join("\n"));
      if (copyFeedback) {
        copyFeedback.textContent = `${notes.length} notas copiadas.`;
      }
    } catch (error) {
      if (copyFeedback) {
        copyFeedback.textContent = "No se pudieron copiar las notas.";
      }
    }
  });
}

updateProcessButton();
