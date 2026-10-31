import { BrowserExtension, Clipboard, environment, open, showToast, Toast } from "@raycast/api";
import { uoinkAndReport } from "./lib/capture";
import { asHttpUrl } from "./lib/uoink";

const BROWSER_EXTENSION_URL = "https://www.raycast.com/browser-extension";

async function activeTabUrl(): Promise<string | undefined> {
  // The Browser Extension API isn't available on Windows yet; canAccess is false there.
  if (!environment.canAccess(BrowserExtension)) {
    return undefined;
  }
  try {
    const tabs = await BrowserExtension.getTabs();
    return asHttpUrl(tabs.find((tab) => tab.active)?.url);
  } catch {
    return undefined;
  }
}

/** Save the link on the clipboard, or else the page in the browser's active tab. */
export default async function UoinkThisUrl() {
  const url = asHttpUrl(await Clipboard.readText()) ?? (await activeTabUrl());
  if (url) {
    await uoinkAndReport(url);
    return;
  }
  const tabsAvailable = environment.canAccess(BrowserExtension);
  await showToast({
    style: Toast.Style.Failure,
    title: "No link to uoink",
    message: tabsAvailable
      ? "Copy a link, or open the page in your browser, then try again."
      : "Copy a link, then try again.",
    primaryAction:
      process.platform === "darwin" && !tabsAvailable
        ? { title: "Get Raycast Browser Extension", onAction: () => open(BROWSER_EXTENSION_URL) }
        : undefined,
  });
}
