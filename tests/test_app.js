const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function element(properties = {}) {
  return {
    hidden: false,
    disabled: false,
    value: "",
    listeners: {},
    classList: { add() {}, remove() {} },
    addEventListener(event, callback) { this.listeners[event] = callback; },
    ...properties,
  };
}

async function main() {
  const fileLabel = element();
  const dropzone = element({ querySelector: () => fileLabel });
  const inputs = ["docente", "blackboard"].map((slot) => element({
    id: `${slot}-file`,
    files: [],
    dataset: { existingName: `${slot}.csv` },
    closest: () => dropzone,
  }));
  const selects = [element(), element()];
  const button = element();
  const copyButton = element();
  const docenteRemoveForm = element({ action: "/clear/docente" });
  const blackboardRemoveForm = element({ action: "/clear/blackboard" });
  const result = element();
  const matchFeedback = element({ dataset: { ready: "true" } });
  const gradeSelection = element();
  const feedback = element();
  const elements = {
    "#process-form": element({ hasAttribute: () => false }),
    "#process-button": button,
    "#process-label": element(),
    "#copy-notes-button": copyButton,
    "#copy-feedback": feedback,
    "#generated-result": result,
    "#match-feedback": matchFeedback,
    "#grade-selection": gradeSelection,
    "#process-error": element(),
    "#docente-name": element(),
    "#blackboard-name": element(),
    "#docente-prompt": element(),
    "#blackboard-prompt": element(),
    "#docente-error": element(),
    "#blackboard-error": element(),
    "#docente-remove": element({ form: docenteRemoveForm }),
    "#blackboard-remove": element({ form: blackboardRemoveForm }),
  };
  let copied;
  const context = {
    document: {
      querySelector: (selector) => elements[selector],
      querySelectorAll: (selector) => ({
        ".upload-input": inputs,
        "#grade-selection select": selects,
        "#result-table tbody .note-cell": [{ textContent: "55" }, { textContent: "64" }, { textContent: "10" }, { textContent: "" }],
      })[selector],
    },
    window: element({ isSecureContext: true }),
    navigator: { clipboard: { writeText: async (value) => { copied = value; } } },
  };
  vm.runInNewContext(fs.readFileSync("static/app.js", "utf8"), context);
  assert.equal(button.disabled, true, "Both selections are required");
  selects[0].value = "4";
  selects[0].listeners.change();
  assert.equal(button.disabled, true);
  selects[1].value = "6";
  selects[1].listeners.change();
  assert.equal(button.disabled, false);
  assert.equal(result.hidden, true, "Changing evaluation hides stale results");
  assert.equal(matchFeedback.dataset.ready, "false", "Changing evaluation returns match details to the pending state");

  inputs[0].files = [{ name: "replacement.xlsx" }];
  inputs[0].listeners.change();
  assert.equal(elements["#process-label"].textContent, "Cargar archivos");
  assert.equal(button.disabled, false);
  assert.equal(gradeSelection.hidden, true);
  assert.equal(elements["#docente-name"].textContent, "replacement.xlsx");
  assert.ok(selects.every((select) => select.disabled), "Old selections do not block replacing files");
  inputs[0].files = [];
  inputs[0].listeners.change();
  assert.equal(gradeSelection.hidden, false);
  assert.ok(selects.every((select) => !select.disabled));
  assert.equal(elements["#process-label"].textContent, "Generar listado");

  await copyButton.listeners.click();
  assert.equal(copied, "55\n64\n10", "Copy uses selected grade cells in roster order and omits summary blanks");
  assert.equal(feedback.textContent, "3 notas copiadas.");
  console.log("OK: selection, replacement, stale results and copying notes");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
