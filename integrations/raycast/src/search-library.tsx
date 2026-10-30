import { Action, ActionPanel, Icon, Keyboard, launchCommand, LaunchType, List } from "@raycast/api";
import { useCachedPromise, usePromise } from "@raycast/utils";
import { useRef, useState } from "react";
import { ItemDetail } from "./components/item-detail";
import { ErrorView } from "./lib/feedback";
import { formatTimestamp, hitCitation, listRecent, RecentItem, SearchHit, searchLibrary } from "./lib/uoink";

const MATCH_LABELS: Record<SearchHit["evidence_kind"], string> = {
  timed_clip: "Timed transcript passage",
  text_only: "Text passage",
  discovery_hint: "Title or metadata match",
};

const MATCH_ICONS: Record<SearchHit["evidence_kind"], Icon> = {
  timed_clip: Icon.Clock,
  text_only: Icon.Text,
  discovery_hint: Icon.MagnifyingGlass,
};

export default function SearchLibrary() {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const abortable = useRef<AbortController>(null);

  const recent = usePromise(() => listRecent(30), [], { onError: () => undefined });
  const search = useCachedPromise(
    (q: string) => searchLibrary(q, 20, { signal: abortable.current?.signal }),
    [trimmed],
    { execute: trimmed.length > 0, keepPreviousData: true, abortable, onError: () => undefined },
  );

  const searching = trimmed.length > 0;
  const error = searching ? search.error : recent.error;
  const hits = searching ? (search.data?.hits ?? []) : [];
  const recentItems = searching ? [] : (recent.data ?? []);

  return (
    <List
      isLoading={searching ? search.isLoading : recent.isLoading}
      onSearchTextChange={setQuery}
      searchBarPlaceholder="Search your Uoink library"
      isShowingDetail={searching && hits.length > 0}
      throttle
    >
      {error ? (
        <ErrorView error={error} />
      ) : searching ? (
        <>
          <List.EmptyView
            icon={Icon.MagnifyingGlass}
            title={search.isLoading ? "Searching…" : `No matches for “${trimmed}”`}
            description="Try fewer or different words. Uoink searches transcripts, articles and notes you've saved."
          />
          <List.Section title="Results" subtitle={hits.length ? String(hits.length) : undefined}>
            {hits.map((hit) => (
              <HitItem key={`${hit.item_id}:${hit.start ?? "text"}`} hit={hit} />
            ))}
          </List.Section>
        </>
      ) : (
        <>
          <List.EmptyView
            icon={Icon.Download}
            title="Your library is empty"
            description="Uoink a YouTube video, podcast, article or thread to start your library."
            actions={
              <ActionPanel>
                <Action
                  title="Uoink Link"
                  icon={Icon.Download}
                  onAction={() => launchCommand({ name: "uoink-link", type: LaunchType.UserInitiated })}
                />
              </ActionPanel>
            }
          />
          <List.Section title="Recently Uoinked">
            {recentItems.map((item) => (
              <RecentListItem key={item.slug} item={item} />
            ))}
          </List.Section>
        </>
      )}
    </List>
  );
}

function hitMarkdown(hit: SearchHit): string {
  const quote = hit.preview.text.trim() || hit.title;
  return `## ${hit.title}\n\n> ${quote.replace(/\r?\n/g, "\n> ")}${hit.preview.truncated ? " …" : ""}`;
}

function HitItem({ hit }: { hit: SearchHit }) {
  const stamp = formatTimestamp(hit.start);
  const link = hit.deep_link ?? hit.source_link;
  return (
    <List.Item
      title={hit.title}
      icon={MATCH_ICONS[hit.evidence_kind] ?? Icon.Document}
      accessories={stamp ? [{ tag: stamp }] : undefined}
      detail={
        <List.Item.Detail
          markdown={hitMarkdown(hit)}
          metadata={
            <List.Item.Detail.Metadata>
              {hit.channel ? <List.Item.Detail.Metadata.Label title="From" text={hit.channel} /> : null}
              {stamp && hit.deep_link ? (
                <List.Item.Detail.Metadata.Link title="Moment" target={hit.deep_link} text={stamp} />
              ) : null}
              <List.Item.Detail.Metadata.Label title="Match" text={MATCH_LABELS[hit.evidence_kind]} />
              {hit.source_link ? (
                <List.Item.Detail.Metadata.Link title="Source" target={hit.source_link} text="Open" />
              ) : null}
            </List.Item.Detail.Metadata>
          }
        />
      }
      actions={
        <ActionPanel>
          {link ? (
            <Action.OpenInBrowser title={stamp && hit.deep_link ? `Open at ${stamp}` : "Open Source"} url={link} />
          ) : null}
          <Action.Push
            title="Show Item"
            icon={Icon.Sidebar}
            target={<ItemDetail selector={{ itemId: hit.item_id }} title={hit.title} />}
          />
          <Action.CopyToClipboard
            title="Copy Citation"
            content={hitCitation(hit)}
            shortcut={Keyboard.Shortcut.Common.Copy}
          />
          <Action.Paste
            title="Paste Citation"
            content={hitCitation(hit)}
            shortcut={{
              macOS: { modifiers: ["cmd", "shift"], key: "v" },
              Windows: { modifiers: ["ctrl", "shift"], key: "v" },
            }}
          />
          {link ? (
            <Action.CopyToClipboard title="Copy Link" content={link} shortcut={Keyboard.Shortcut.Common.CopyDeeplink} />
          ) : null}
          <Action.CopyToClipboard title="Copy Item ID" content={hit.item_id} />
        </ActionPanel>
      }
    />
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
