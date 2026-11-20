// Playwright config for the Uoink QA smoke suite. Run it through
// scripts/qa_smoke.py, which seeds an isolated library, starts the helper
// hidden and sets the UOINK_QA_* variables these tests read.
import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const runDir = process.env.UOINK_QA_RUN_DIR || path.resolve(here, "..", "..", "_scratch", "qa-smoke", "manual");
const state = process.env.UOINK_QA_STATE || "seeded";
const label = process.env.UOINK_QA_REPORT_LABEL || state;

const dashboard = /(dashboard|a11y)\.spec\.mjs$/;
const variant = (name, width, height, colorScheme) => ({
  name,
  testMatch: dashboard,
  use: { viewport: { width, height }, colorScheme },
});

export default defineConfig({
  testDir: here,
  outputDir: path.join(runDir, "pw-output", label),
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // One helper and one library per run: tests share state (a settings switch,
  // a shelf move), so they run one at a time in a fixed order.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(runDir, "reports", `${label}.json`) }],
  ],
  use: {
    // Playwright's own Chromium in the new headless mode: no window at all.
    channel: "chromium",
    headless: true,
    reducedMotion: "reduce",
    serviceWorkers: "block",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    variant("light-1280", 1280, 900, "light"),
    variant("dark-1280", 1280, 900, "dark"),
    variant("light-390", 390, 844, "light"),
    variant("dark-390", 390, 844, "dark"),
    { name: "extension", testMatch: /extension\.spec\.mjs$/ },
  ],
});
