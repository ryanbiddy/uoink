import { Action, ActionPanel, Icon, Keyboard, List } from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { useRef, useState } from "react";
import { ItemDetail } from "./components/item-detail";
import { ErrorView } from "./lib/feedback";
import { formatTimestamp, hitCitation, SearchHit, searchLibrary } from "./lib/uoink";

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

  const search = useCachedPromise(
    (q: string) => searchLibrary(q, 20, { signal: abortable.current?.signal }),
    [trimmed],
    { execute: trimmed.length > 0, keepPreviousData: true, abortable, onError: () => undefined },
  );

  const searching = trimmed.length > 0;
  const hits = searching ? (search.data?.hits ?? []) : [];

  return (
    <List
      isLoading={searching && search.isLoading}
      onSearchTextChange={setQuery}
      searchBarPlaceholder="Search your Uoink library"
      isShowingDetail={hits.length > 0}
      throttle
    >
      {searching && search.error ? (
        <ErrorView error={search.error} />
      ) : !searching ? (
        <List.EmptyView
          icon={Icon.MagnifyingGlass}
          title="Search your Uoink library"
          description="Type a few words. Uoink searches the transcripts, articles and notes you've saved."
        />
      ) : (
        <>
          <List.EmptyView
            icon={Icon.MagnifyingGlass}
            title={search.isLoading ? "Searching…" : `No matches for “${trimmed}”`}
            description="Try fewer or different words."
          />
          <List.Section title="Results" subtitle={hits.length ? String(hits.length) : undefined}>
            {hits.map((hit) => (
              <HitItem key={`${hit.item_id}:${hit.start ?? "text"}`} hit={hit} />
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
          <Action.CopyToClipboard title="Copy Citation" content={hitCitation(hit)} />
          {link ? (
            <Action.OpenInBrowser
              title={stamp && hit.deep_link ? `Open at ${stamp}` : "Open Source"}
              url={link}
              shortcut={Keyboard.Shortcut.Common.Open}
            />
          ) : null}
          <Action.Paste
            title="Paste Citation"
            content={hitCitation(hit)}
            shortcut={{
              macOS: { modifiers: ["cmd", "shift"], key: "v" },
              Windows: { modifiers: ["ctrl", "shift"], key: "v" },
            }}
          />
          <Action.Push
            title="Show Item"
            icon={Icon.Sidebar}
            target={<ItemDetail selector={{ itemId: hit.item_id }} title={hit.title} />}
            shortcut={{
              macOS: { modifiers: ["cmd"], key: "i" },
              Windows: { modifiers: ["ctrl"], key: "i" },
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
