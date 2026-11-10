const processForm = document.querySelector("#process-form");
const processButton = document.querySelector("#process-button");
const processLabel = document.querySelector("#process-label");
const processError = document.querySelector("#process-error");
const columnError = document.querySelector("#column-error");
const fileInputs = Array.from(document.querySelectorAll(".upload-input"));
const gradeSelection = document.querySelector("#grade-selection");
const gradeSelects = Array.from(document.querySelectorAll("#grade-selection select"));
const result = document.querySelector("#generated-result");
const matchFeedback = document.querySelector("#match-feedback");
const copyNotesButton = document.querySelector("#copy-notes-button");
const copyFeedback = document.querySelector("#copy-feedback");
const maxUploadSize = 16 * 1024 * 1024;

function hasNewFile() {
  return fileInputs.some((input) => input.files.length > 0);
}

function updateProcessButton() {
  const uploading = hasNewFile();
  const filesReady = fileInputs.every((input) => input.files.length > 0 || input.dataset.existingName);
  const choosingGrades = Boolean(gradeSelection && filesReady && !uploading);
  if (gradeSelection) gradeSelection.hidden = !choosingGrades;
  gradeSelects.forEach((select) => { select.disabled = !choosingGrades; });
  processLabel.textContent = choosingGrades ? "Generar listado" : "Cargar archivos";
  processButton.disabled = !filesReady || (!uploading && (!choosingGrades || gradeSelects.some((select) => !select.value)));
}

function hideResult() {
  if (result) result.hidden = true;
  matchFeedback.dataset.ready = "false";
}

function showError(element, message) {
  element.textContent = message;
  element.hidden = !message;
}

function fileValidationError(file) {
  if (!file) return "";
  if (!/\.(xls|xlsx|csv)$/i.test(file.name)) return "Elige un archivo .xls, .xlsx o .csv.";
  if (file.size >= maxUploadSize) return "El archivo debe pesar menos de 16 MiB.";
  return "";
}

fileInputs.forEach((input) => {
  const slot = input.id.replace("-file", "");
  const name = document.querySelector(`#${slot}-name`);
  const prompt = document.querySelector(`#${slot}-prompt`);
  const error = document.querySelector(`#${slot}-error`);
  const removeButton = document.querySelector(`#${slot}-remove`);
  const removeForm = removeButton.form;
  const dropzone = input.closest(".upload-control");
  const picker = dropzone.querySelector(".file-label");

  function updateFile() {
    const filename = input.files[0]?.name || input.dataset.existingName;
    name.textContent = filename;
    name.hidden = !filename;
    prompt.hidden = Boolean(filename);
    removeButton.hidden = !filename;
    picker.title = filename ? "Cambiar archivo" : "Seleccionar archivo";
  }

  input.addEventListener("change", () => {
    const message = fileValidationError(input.files[0]);
    showError(error, message);
    showError(processError, "");
    if (message) input.value = "";
    if (!message) hideResult();
    updateFile();
    updateProcessButton();
  });

  removeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (processForm.inert || processForm.hasAttribute("aria-busy")) return;

    if (input.dataset.existingName) {
      processForm.inert = true;
      if (result) result.inert = true;
      try {
        const response = await fetch(removeForm.action, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        if (response.status !== 204) throw new Error("No se pudo quitar el archivo.");
      } catch {
        showError(error, "No se pudo quitar el archivo. Inténtalo de nuevo.");
        return;
      } finally {
        processForm.inert = false;
        if (result) result.inert = false;
        removeButton.focus();
      }
      input.dataset.existingName = "";
      input.required = true;
      if (columnError) columnError.hidden = true;
    }

    input.value = "";
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.focus();
  });

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
  dropzone.addEventListener("dragleave", (event) => {
    if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove("is-dragging");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
    const files = event.dataTransfer.files;
    if (!files.length) return;

    const message = files.length > 1 ? "Carga un solo archivo en cada recuadro." : fileValidationError(files[0]);
    if (message) {
      showError(error, message);
      return;
    }
    input.files = files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  window.addEventListener("pageshow", updateFile);
});

gradeSelects.forEach((select) => {
  select.addEventListener("change", () => {
    hideResult();
    showError(processError, "");
    updateProcessButton();
  });
});

processForm.addEventListener("submit", (event) => {
  if (processForm.inert || processForm.hasAttribute("aria-busy")) {
    event.preventDefault();
    return;
  }
  const totalSize = fileInputs.reduce((total, input) => total + (input.files[0]?.size || 0), 0);
  if (totalSize >= maxUploadSize) {
    event.preventDefault();
    showError(processError, "Los dos archivos juntos deben pesar menos de 16 MiB.");
    return;
  }
  processForm.setAttribute("aria-busy", "true");
  processLabel.textContent = hasNewFile() ? "Cargando archivos…" : "Generando listado…";
  processButton.disabled = true;
});

window.addEventListener("pageshow", () => {
  processForm.removeAttribute("aria-busy");
  updateProcessButton();
});

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "");
  helper.style.position = "fixed";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  try {
    helper.select();
    if (!document.execCommand("copy")) throw new Error("No se pudo copiar.");
  } finally {
    helper.remove();
    copyNotesButton.focus();
  }
}

if (copyNotesButton) {
  copyNotesButton.addEventListener("click", async () => {
    const noteCells = document.querySelectorAll("#result-table tbody .note-cell");
    const notes = Array.from(noteCells, (cell) => cell.textContent.trim()).filter(Boolean);
    if (!notes.length) {
      copyFeedback.textContent = "No hay notas para copiar.";
      return;
    }

    try {
      await copyText(notes.join("\n"));
      copyFeedback.textContent = notes.length === 1 ? "1 nota copiada." : `${notes.length} notas copiadas.`;
    } catch {
      copyFeedback.textContent = "No se pudieron copiar las notas.";
    }
  });
}

updateProcessButton();
