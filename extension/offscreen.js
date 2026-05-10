// Offscreen document — two jobs:
//   1) Clipboard: write text via execCommand('copy'). The offscreen doc is
//      the only MV3 context where a service worker can reach the clipboard.
//   2) Theme detection: window.matchMedia is unavailable in MV3 service
//      workers, so the SW delegates prefers-color-scheme detection here and
//      we push change events back so it can swap the toolbar icon.

const themeMq = window.matchMedia("(prefers-color-scheme: dark)");

function pushTheme() {
  // SW may be asleep; failures are fine — it will queryTheme on next wake.
  chrome.runtime.sendMessage({
    type: "themeChanged",
    isDark: themeMq.matches,
  }).catch(() => { /* ignore */ });
}

themeMq.addEventListener("change", pushTheme);
pushTheme();

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.target !== "offscreen") return; // not for us

  if (msg.type === "copy") {
    try {
      const ta = document.getElementById("sink");
      ta.value = msg.text || "";
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      ta.value = "";
      sendResponse({ ok });
    } catch (e) {
      sendResponse({ ok: false, error: String(e) });
    }
    return; // synchronous response
  }

  if (msg.type === "queryTheme") {
    sendResponse({ isDark: themeMq.matches });
    return; // synchronous response
  }
});
