"use strict";
globalThis.UoinkStore = {
  url(config) {
    const id = config && config.chrome_web_store_id;
    const url = config && config.chrome_web_store_url;
    if (typeof id !== "string" || id.length !== 32 || !/^[a-p]{32}$/.test(id)
        || typeof url !== "string" || url !== url.trim()) return "";
    return new RegExp("^https://chromewebstore\\.google\\.com/detail/(?:[a-z0-9-]+/)?" + id + "$").test(url) ? url : "";
  },
  async load() {
    try {
      const response = await fetch(chrome.runtime.getURL("store-config.json"));
      if (!response.ok) return "";
      return this.url(await response.json());
    } catch { return ""; }
  },
};
