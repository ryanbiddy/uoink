import { Action, ActionPanel, Icon, List, open, openExtensionPreferences } from "@raycast/api";
import { showFailureToast } from "@raycast/utils";
import { INSTALL_URL, UoinkMissingError } from "./uoink";

export function showUoinkFailure(error: unknown, title: string) {
  if (error instanceof UoinkMissingError) {
    return showFailureToast(error, {
      title: "Uoink isn't set up",
      primaryAction: { title: "Install Uoink", onAction: () => open(INSTALL_URL) },
    });
  }
  return showFailureToast(error, { title });
}

export function SetupActions() {
  return (
    <>
      <Action.OpenInBrowser title="Install Uoink" url={INSTALL_URL} />
      <Action title="Set CLI Path" icon={Icon.Gear} onAction={openExtensionPreferences} />
    </>
  );
}

/** Replaces the list when the CLI is missing or the library can't be read. */
export function ErrorView({ error }: { error: Error }) {
  const missing = error instanceof UoinkMissingError;
  return (
    <List.EmptyView
      icon={missing ? Icon.Download : Icon.Warning}
      title={missing ? "Uoink isn't set up" : "Uoink couldn't read your library"}
      description={error.message}
      actions={
        <ActionPanel>
          <SetupActions />
        </ActionPanel>
      }
    />
  );
}
