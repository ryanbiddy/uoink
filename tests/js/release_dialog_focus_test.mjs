import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
function source(name) {
  return page.match(new RegExp("    (?:async )?function " + name + "\\([^]*?\\n    \\}"))[0];
}

test("hook guide traps focus immediately and restores it even during loading", async () => {
  const document = {};
  const control = () => ({ focus() { document.activeElement = this; } });
  const opener = control(), close = control();
  const modal = { classList: { add() {}, remove() {} } };
  const els = {hookExplainer: modal, hookExplainerClose: close,
    hookExplainerList: {querySelector: () => null}};
  let loaded;
  const ctx = vm.createContext({ state: {}, els, document, focusableElements: () => [close],
    loadHookGuide: () => new Promise(resolve => { loaded = resolve; }) });
  vm.runInContext(["restoreFocus", "trapModalFocus", "openHookExplainer", "closeHookExplainer"].map(source).join("\n"), ctx);
  for (const escape of [true, false]) {
    opener.focus();
    const opening = ctx.openHookExplainer("example", opener);
    assert.equal(document.activeElement, close);
    let caught = false;
    ctx.trapModalFocus({key: "Tab", preventDefault() { caught = true; }}, modal, ctx.closeHookExplainer);
    assert.equal(caught, true);
    if (escape) ctx.trapModalFocus({key: "Escape", preventDefault() {}}, modal, ctx.closeHookExplainer);
    else ctx.closeHookExplainer();
    loaded([]);
    await opening;
    assert.equal(document.activeElement, opener);
  }
});
