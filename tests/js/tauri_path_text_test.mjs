import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

test("Windows opens web links without a command interpreter", () => {
  const source = readFileSync("tauri-ui/src-tauri/src/main.rs", "utf8");
  const openUrl = source.split("fn open_url(")[1].split("#[tauri::command]")[0];
  assert.doesNotMatch(openUrl, /Command::new\("cmd(?:\.exe)?"\)/i);
  assert.match(openUrl, /Command::new\("explorer\.exe"\);\s*c\.arg\(&url\)/);
});

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
