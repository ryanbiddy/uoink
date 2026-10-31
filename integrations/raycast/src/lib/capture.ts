import { Clipboard, getPreferenceValues, showHUD, showToast, Toast } from "@raycast/api";
import { showUoinkFailure } from "./feedback";
import { captureLabel, captureUrl } from "./uoink";

/** Capture one link, then report the result. The CLI returns once the capture is saved. */
export async function uoinkAndReport(url: string): Promise<void> {
  await showToast({ style: Toast.Style.Animated, title: "Uoinking…", message: url });
  try {
    const result = await captureUrl(url);
    const { copyAfterCapture } = getPreferenceValues<Preferences>();
    const copied = Boolean(copyAfterCapture && result.corpus_md);
    if (copied && result.corpus_md) {
      await Clipboard.copy(result.corpus_md);
    }
    const label = captureLabel(result);
    if (result.job_id) {
      await showHUD(`Queued in Uoink: ${label}`);
    } else {
      await showHUD(copied ? `Uoinked ${label}. Markdown copied` : `Uoinked ${label}`);
    }
  } catch (error) {
    await showUoinkFailure(error, "Couldn't uoink that link");
  }
}
