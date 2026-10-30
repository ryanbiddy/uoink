import { Clipboard, getSelectedText, LaunchProps, showToast, Toast } from "@raycast/api";
import { uoinkAndReport } from "./lib/capture";
import { asHttpUrl } from "./lib/uoink";

async function selectedText(): Promise<string | undefined> {
  try {
    return await getSelectedText();
  } catch {
    return undefined;
  }
}

export default async function UoinkLink(props: LaunchProps<{ arguments: Arguments.UoinkLink }>) {
  const typed = props.arguments.url?.trim();
  if (typed) {
    const url = asHttpUrl(typed);
    if (!url) {
      await showToast({ style: Toast.Style.Failure, title: "That isn't a web link", message: typed });
      return;
    }
    await uoinkAndReport(url);
    return;
  }
  // No argument: use a selected link, then the clipboard.
  const url = asHttpUrl(await selectedText()) ?? asHttpUrl(await Clipboard.readText());
  if (!url) {
    await showToast({
      style: Toast.Style.Failure,
      title: "No link to uoink",
      message: "Type a link, select one, or copy one first.",
    });
    return;
  }
  await uoinkAndReport(url);
}
