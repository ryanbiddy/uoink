import "./styles.css";

const steps = [
  { id: "welcome", rail: "Prep" },
  { id: "location", rail: "Prep" },
  { id: "ready", rail: "Install" },
  { id: "installing", rail: "Install" },
  { id: "migrating", rail: "Migrate" },
  { id: "finished", rail: "Done" },
];

const state = {
  screen: "welcome",
  installDir: "C:\\Users\\%USERNAME%\\AppData\\Local\\Uoink",
  legacyFound: true,
  log: [
    "ready: Tauri shell owns UX",
    "ready: Inno handles file operations in silent mode",
  ],
  progress: 0,
  migration: [
    { label: "index.db", status: "done" },
    { label: "Settings", status: "done" },
    { label: "topics.json", status: "done" },
    { label: "corpus", status: "active" },
  ],
};

function invoke(command, args = {}) {
  const api = window.__TAURI__ && window.__TAURI__.tauri;
  if (!api || !api.invoke) {
    console.info(`[prototype] invoke ${command}`, args);
    return Promise.resolve({ ok: true, prototype: true });
  }
  return api.invoke(command, args);
}

function markSvg() {
  return `
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <path d="M14 6 H40 V62 a10 10 0 0 0 20 0 V6 H86 V62 a36 36 0 0 1 -72 0 Z" fill="#C2410C"/>
      <rect x="14" y="6" width="26" height="14" fill="#FFF4EC"/>
      <rect x="60" y="6" width="26" height="14" fill="#FFF4EC"/>
      <path d="M43 78 L57 78 L50 91 Z" fill="#FFD23F"/>
    </svg>
  `;
}

function setScreen(screen) {
  state.screen = screen;
  render();
}

function rail() {
  const activeIndex = steps.findIndex((step) => step.id === state.screen);
  const railSteps = ["Prep", "Install", "Migrate", "Done"];
  const activeRail = steps[activeIndex]?.rail || "Prep";
  const activeRailIndex = railSteps.indexOf(activeRail);
  return `
    <div class="rail" aria-label="Install progress">
      ${railSteps.map((label, index) => `
        <div class="rail-step ${index < activeRailIndex ? "done" : ""} ${label === activeRail ? "active" : ""}">
          <span>${index + 1}</span>
          <b>${label}</b>
        </div>
      `).join("")}
    </div>
  `;
}

function titlebar() {
  return `
    <header class="titlebar ${state.screen === "welcome" ? "welcome" : ""}" data-tauri-drag-region>
      <div class="brand">${markSvg()}<span>UOINK</span></div>
      <div class="window-actions">
        <button type="button" data-action="minimize" aria-label="Minimize"></button>
        <button type="button" data-action="close" aria-label="Close"></button>
      </div>
    </header>
  `;
}

function welcome() {
  return `
    <section class="screen welcome-screen">
      <div class="hero-mark">${markSvg()}</div>
      <h1>Uoink that <em>shit.</em></h1>
      <p>YouTube becomes a local, searchable research corpus for your AI agents. No cloud account. No sync layer. Your machine does the work.</p>
      <button class="cta" type="button" data-next="location">Let's go -></button>
    </section>
  `;
}

function location() {
  return `
    <section class="screen">
      ${rail()}
      <div class="two-col">
        <div>
          <div class="eyebrow">Install location</div>
          <h2>Choose where Uoink lives.</h2>
          <p class="lede">The Tauri shell passes this location to Inno in silent mode. The Python helper, dashboard assets, and tray app still install through the proven installer path.</p>
        </div>
        <div class="card">
          <label>Install folder</label>
          <div class="path-row">
            <input value="${state.installDir}" data-install-dir>
            <button type="button" data-action="browse">Browse</button>
          </div>
          <div class="free-space">Free space readout: prototype hook ready</div>
          ${state.legacyFound ? `<div class="notice">Legacy local data detected. Migration will run after install and keep a grace copy.</div>` : ""}
        </div>
      </div>
      <footer><button class="ghost" type="button" data-next="welcome">Back</button><button class="cta" type="button" data-next="ready">Continue -></button></footer>
    </section>
  `;
}

function ready() {
  const items = [
    "Python helper + local loopback API",
    "Tray app with dashboard and splash windows",
    "Chrome extension-facing assets",
    "MCP tools and Uoink Operator Skill",
  ];
  return `
    <section class="screen">
      ${rail()}
      <div class="eyebrow">Ready</div>
      <h2>Install the local stack.</h2>
      <div class="manifest">
        ${items.map((item) => `<div><span>-></span>${item}</div>`).join("")}
      </div>
      <footer><button class="ghost" type="button" data-next="location">Back</button><button class="cta" type="button" data-action="install">Install Uoink -></button></footer>
    </section>
  `;
}

function installing() {
  return `
    <section class="screen">
      ${rail()}
      <div class="eyebrow">Installing</div>
      <h2>Running the installer.</h2>
      <div class="progress"><span style="width:${state.progress}%"></span></div>
      <pre class="log">${state.log.join("\n")}</pre>
    </section>
  `;
}

function migrating() {
  return `
    <section class="screen">
      ${rail()}
      <div class="eyebrow">Migrating</div>
      <h2>Moving the old pieces carefully.</h2>
      <div class="checklist">
        ${state.migration.map((item) => `
          <div class="${item.status}">
            <span>${item.status === "done" ? "OK" : "->"}</span>
            <b>${item.label}</b>
            ${item.label === "corpus" ? `<div class="nested"><span style="width:72%"></span></div>` : ""}
          </div>
        `).join("")}
      </div>
      <footer><button class="cta" type="button" data-next="finished">Finish migration</button></footer>
    </section>
  `;
}

function finished() {
  return `
    <section class="screen finish-screen">
      ${rail()}
      <div class="big-mark">${markSvg()}</div>
      <h2>Uoink is running.</h2>
      <div class="status-pill">Uoink is running OK</div>
      <div class="cta-grid">
        <button type="button" data-action="youtube">Open YouTube</button>
        <button type="button" data-action="dashboard">Open Dashboard</button>
        <button type="button" data-action="quickstart">Quick start</button>
      </div>
    </section>
  `;
}

function screenHtml() {
  if (state.screen === "welcome") return welcome();
  if (state.screen === "location") return location();
  if (state.screen === "ready") return ready();
  if (state.screen === "installing") return installing();
  if (state.screen === "migrating") return migrating();
  return finished();
}

function render() {
  document.querySelector("#app").innerHTML = `${titlebar()}<main>${screenHtml()}</main>`;
}

async function simulateInstall() {
  state.log.push(`install dir: ${state.installDir}`);
  state.progress = 8;
  setScreen("installing");
  const ticks = [
    ["launching Inno in silent mode", 22],
    ["copying helper runtime", 48],
    ["installing tray + dashboard assets", 72],
    ["writing Run key", 88],
    ["installer finished", 100],
  ];
  for (const [line, progress] of ticks) {
    await new Promise((resolve) => setTimeout(resolve, 380));
    state.log.push(line);
    state.progress = progress;
    render();
  }
  await invoke("run_inno_silent", { installDir: state.installDir });
  setScreen("migrating");
}

document.addEventListener("click", async (event) => {
  const next = event.target.closest("[data-next]");
  if (next) return setScreen(next.dataset.next);
  const action = event.target.closest("[data-action]");
  if (!action) return;
  if (action.dataset.action === "install") return simulateInstall();
  if (action.dataset.action === "dashboard") return invoke("open_dashboard_window");
  if (action.dataset.action === "youtube") return invoke("open_url", { url: "https://youtube.com" });
  if (action.dataset.action === "quickstart") return invoke("open_url", { url: "https://uoink.video/how" });
  if (action.dataset.action === "browse") return invoke("pick_install_dir").then((dir) => {
    if (dir) {
      state.installDir = dir;
      render();
    }
  });
  if (action.dataset.action === "minimize") return invoke("minimize_window");
  if (action.dataset.action === "close") return invoke("close_window");
});

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-install-dir]")) {
    state.installDir = event.target.value;
  }
});

render();
