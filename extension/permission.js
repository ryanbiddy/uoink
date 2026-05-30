(function () {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const origin = params.get("origin") || "";
  const tabId = parseInt(params.get("tabId") || "0", 10);
  const url = params.get("url") || "";
  const kind = params.get("kind") || "extract";

  const domainEl = document.getElementById("perm-domain");
  if (domainEl && origin) {
    try {
      domainEl.textContent = new URL(origin).hostname;
    } catch {
      domainEl.textContent = origin;
    }
  }

  const cancelBtn = document.getElementById("cancel-btn");
  const allowOnceBtn = document.getElementById("allow-once-btn");
  const allowAlwaysBtn = document.getElementById("allow-always-btn");

  if (cancelBtn) {
    cancelBtn.onclick = () => {
      window.close();
    };
  }

  async function handleGrant(always) {
    if (!origin || !url) {
      window.close();
      return;
    }

    const permissionPattern = origin + "/";

    chrome.permissions.request({
      origins: [permissionPattern]
    }, async (granted) => {
      if (granted) {
        if (always) {
          try {
            const host = new URL(origin).hostname;
            await STC.addAllowedSite(host);
          } catch (e) {
            console.error("Failed to add site to allowlist", e);
          }
        }
        try {
          await chrome.runtime.sendMessage({
            type: "permissionGranted",
            tabId,
            url,
            kind
          });
        } catch (e) {
          console.error("Failed to notify background worker of permission grant", e);
        }
      }
      window.close();
    });
  }

  if (allowOnceBtn) {
    allowOnceBtn.onclick = () => handleGrant(false);
  }

  if (allowAlwaysBtn) {
    allowAlwaysBtn.onclick = () => handleGrant(true);
  }
})();
