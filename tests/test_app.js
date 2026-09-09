const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function element(properties = {}) {
  return {
    hidden: false,
    disabled: false,
    value: "",
    listeners: {},
    classList: { toggle() {} },
    addEventListener(event, callback) { this.listeners[event] = callback; },
    ...properties,
  };
}

async function main() {
  const inputs = [element({ files: [], dataset: { hasExisting: "true" } }), element({ files: [], dataset: { hasExisting: "true" } })];
  const selects = [element(), element()];
  const button = element();
  const copyButton = element();
  const result = element();
  const download = element();
  const feedback = element();
  const status = element();
  const elements = {
    "#process-button": button,
    "#copy-notes-button": copyButton,
    "#copy-feedback": feedback,
    "#generated-result": result,
    ".secondary-download": download,
    "#process-status": status,
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
    window: { isSecureContext: true },
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
  assert.equal(download.hidden, true, "Changing evaluation hides stale download");

  inputs[0].files = [{ name: "replacement.xlsx" }];
  inputs[0].listeners.change();
  assert.equal(button.textContent, "Cargar columnas");
  assert.equal(button.disabled, false);
  assert.ok(selects.every((select) => select.disabled), "Old selections do not block replacing files");
  inputs[0].files = [];
  inputs[0].listeners.change();
  assert.ok(selects.every((select) => !select.disabled));
  assert.equal(button.textContent, "Procesar y generar archivo");

  await copyButton.listeners.click();
  assert.equal(copied, "55\n64\n10", "Copy uses selected grade cells in roster order and omits summary blanks");
  assert.equal(feedback.textContent, "3 notas copiadas.");
  console.log("OK: selection, replacement, stale results and copying notes");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
