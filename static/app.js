const fileInputs = Array.from(document.querySelectorAll(".upload-input"));
const processButton = document.querySelector("#process-button");
const copyNotesButton = document.querySelector("#copy-notes-button");
const copyFeedback = document.querySelector("#copy-feedback");
const gradeSelects = Array.from(document.querySelectorAll("#grade-selection select"));

function markResultStale() {
  const result = document.querySelector("#generated-result");
  const download = document.querySelector(".secondary-download");
  if (result) result.hidden = true;
  if (download) download.hidden = true;
  const status = document.querySelector("#process-status");
  if (status) status.textContent = "La selección cambió. Carga las columnas si reemplazaste archivos y vuelve a generar el resultado.";
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
}

fileInputs.forEach((input) => {
  input.addEventListener("change", () => {
    const label = document.querySelector(`label[for="${input.id}"]`);
    if (label) {
      const defaultLabel = label.dataset.defaultLabel || "Seleccionar archivo";
      label.textContent = input.files && input.files.length > 0 ? input.files[0].name : defaultLabel;
    }

    markResultStale();
    updateProcessButton();
  });
});

gradeSelects.forEach((select) => {
  select.addEventListener("change", () => {
    markResultStale();
    updateProcessButton();
  });
});

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
