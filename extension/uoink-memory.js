// Uoink Memory is now unified into the helper-served dashboard Library tab.
// Keep this extension page as a small compatibility shim for existing popup links.

const DASHBOARD_LIBRARY_URL = "http://127.0.0.1:5179/dashboard?tab=library";

const openDashboard = document.getElementById("open-dashboard");
const copyLink = document.getElementById("copy-link");
const statusLine = document.getElementById("status");

openDashboard.addEventListener("click", () => {
  statusLine.textContent = "Opening the dashboard Library...";
});

copyLink.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(DASHBOARD_LIBRARY_URL);
    statusLine.textContent = "Dashboard link copied.";
  } catch (_) {
    statusLine.textContent = DASHBOARD_LIBRARY_URL;
  }
});

// Log memory_opened engagement event on load
if (typeof STC !== "undefined" && typeof STC.logEngagement === "function") {
  STC.logEngagement("memory_opened", "memory_page").catch((err) => {
    console.warn("[Memory] Failed to log memory_opened:", err);
  });
}

// Stubs for search query engagement tracking if page is extended
async function logSearchHit(query, videoId) {
  if (typeof STC !== "undefined" && typeof STC.logEngagement === "function") {
    return STC.logEngagement("search_hit", "memory_page", { query, video_id: videoId });
  }
}

async function logSearchClick(query, videoId) {
  if (typeof STC !== "undefined" && typeof STC.logEngagement === "function") {
    return STC.logEngagement("search_click", "memory_page", { query, video_id: videoId });
  }
}

