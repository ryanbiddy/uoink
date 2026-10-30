import { BrowserExtension, environment, open, showToast, Toast } from "@raycast/api";
import { uoinkAndReport } from "./lib/capture";
import { asHttpUrl } from "./lib/uoink";

const BROWSER_EXTENSION_URL = "https://www.raycast.com/browser-extension";

async function needBrowserExtension(message: string) {
  await showToast({
    style: Toast.Style.Failure,
    title: "Can't read the browser tab",
    message,
    primaryAction: { title: "Get Raycast Browser Extension", onAction: () => open(BROWSER_EXTENSION_URL) },
  });
}

export default async function UoinkCurrentTab() {
  if (!environment.canAccess(BrowserExtension)) {
    await needBrowserExtension("Install the Raycast browser extension, or use Uoink Link instead.");
    return;
  }
  let tabs: BrowserExtension.Tab[];
  try {
    tabs = await BrowserExtension.getTabs();
  } catch {
    await needBrowserExtension("Open your browser with the Raycast extension enabled, then try again.");
    return;
  }
  const tab = tabs.find((candidate) => candidate.active);
  const url = asHttpUrl(tab?.url);
  if (!url) {
    await showToast({
      style: Toast.Style.Failure,
      title: "No web page in the active tab",
      message: tab?.url ?? "Switch to the tab you want to uoink.",
    });
    return;
  }
  await uoinkAndReport(url);
}
