// Offscreen document — runs only to write text to the clipboard, then the
// service worker tears it down. The execCommand('copy') trick still works
// inside an offscreen doc and doesn't require focus or a user gesture.

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
});
