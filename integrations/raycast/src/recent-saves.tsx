import { Action, ActionPanel, Icon, Keyboard, launchCommand, LaunchType, List } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { ItemDetail } from "./components/item-detail";
import { ErrorView } from "./lib/feedback";
import { listRecent, RecentItem } from "./lib/uoink";

export default function RecentSaves() {
  const { data, isLoading, error } = usePromise(() => listRecent(20), [], { onError: () => undefined });

  return (
    <List isLoading={isLoading} searchBarPlaceholder="Filter recent saves">
      {error ? (
        <ErrorView error={error} />
      ) : (
        <>
          <List.EmptyView
            icon={Icon.Download}
            title="Nothing saved yet"
            description="Copy a YouTube, podcast, article or thread link, then run Uoink This URL."
            actions={
              <ActionPanel>
                <Action
                  title="Uoink This URL"
                  icon={Icon.Download}
                  onAction={() => launchCommand({ name: "uoink-this-url", type: LaunchType.UserInitiated })}
                />
              </ActionPanel>
            }
          />
          {(data ?? []).map((item) => (
            <RecentListItem key={item.slug} item={item} />
          ))}
        </>
      )}
    </List>
  );
}

function RecentListItem({ item }: { item: RecentItem }) {
  const title = item.title || item.slug;
  const saved = item.yoinked_at ? new Date(item.yoinked_at) : undefined;
  return (
    <List.Item
      title={title}
      icon={Icon.Document}
      accessories={saved && !Number.isNaN(saved.getTime()) ? [{ date: saved, tooltip: "Saved" }] : undefined}
      actions={
        <ActionPanel>
          <Action.Push
            title="Show Item"
            icon={Icon.Sidebar}
            target={<ItemDetail selector={{ slug: item.slug }} title={title} />}
          />
          {item.folder ? <Action.ShowInFinder path={item.folder} /> : null}
          <Action.CopyToClipboard title="Copy Slug" content={item.slug} shortcut={Keyboard.Shortcut.Common.CopyName} />
        </ActionPanel>
      }
    />
  );
}
