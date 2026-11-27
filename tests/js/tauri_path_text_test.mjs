import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

test("the installer keeps entered text in DOM properties", () => {
  const app = {}, field = {}, log = {};
  const document = {
    addEventListener() {},
    querySelector: selector => ({ "#app": app, "[data-install-dir]": field, ".log": log })[selector],
  };
  const ctx = vm.createContext({ document, window: {} });
  vm.runInContext(readFileSync("tauri-ui/src/main.js", "utf8").replace('import "./styles.css";', ""), ctx);
  const sample = "library <examples> & notes";
  ctx.sample = sample;
  vm.runInContext('state.installDir = sample; setScreen("location")', ctx);
  assert.ok(!app.innerHTML.includes(sample));
  assert.equal(field.value, sample);
  vm.runInContext('state.log.push(sample); setScreen("installing")', ctx);
  assert.ok(!app.innerHTML.includes(sample));
  assert.ok(log.textContent.includes(sample));
});
