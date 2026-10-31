import { Action, ActionPanel, Detail, Icon, Keyboard } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { getItem, itemMarkdown, formatTimestamp, quoteCitation } from "../lib/uoink";
import { SetupActions } from "../lib/feedback";

type Selector = { itemId: string } | { slug: string };

export function ItemDetail({ selector, title }: { selector: Selector; title?: string }) {
  const { data, isLoading, error } = usePromise((s: Selector) => getItem(s), [selector]);

  if (error) {
    return (
      <Detail
        navigationTitle={title}
        markdown={`# Couldn't open this item\n\n${error.message}`}
        actions={
          <ActionPanel>
            <SetupActions />
          </ActionPanel>
        }
      />
    );
  }

  const card = data?.card;
  const markdown = data ? itemMarkdown(data) : "";
  const excerpts = card?.excerpts ?? [];
  const name = card?.title || title || "Untitled";

  return (
    <Detail
      isLoading={isLoading}
      navigationTitle={title}
      markdown={markdown}
      metadata={
        card ? (
          <Detail.Metadata>
            {card.channel ? <Detail.Metadata.Label title="From" text={card.channel} /> : null}
            {card.platform ? <Detail.Metadata.Label title="Platform" text={card.platform} /> : null}
            {card.topic ? <Detail.Metadata.Label title="Topic" text={card.topic} /> : null}
            {card.yoinked_at ? <Detail.Metadata.Label title="Saved" text={card.yoinked_at.slice(0, 10)} /> : null}
            {data?.source_link ? <Detail.Metadata.Link title="Source" target={data.source_link} text="Open" /> : null}
            <Detail.Metadata.Label title="Item ID" text={data?.item_id ?? ""} />
          </Detail.Metadata>
        ) : null
      }
      actions={
        data ? (
          <ActionPanel>
            {data.source_link ? <Action.OpenInBrowser title="Open Source" url={data.source_link} /> : null}
            <Action.CopyToClipboard
              title="Copy as Markdown"
              content={markdown}
              shortcut={Keyboard.Shortcut.Common.Copy}
            />
            <Action.Paste title="Paste as Markdown" content={markdown} />
            {excerpts.length ? (
              <ActionPanel.Submenu title="Copy Excerpt Citation…" icon={Icon.QuotationMarks}>
                {excerpts.map((excerpt) => (
                  <Action.CopyToClipboard
                    key={excerpt.excerpt_id}
                    title={formatTimestamp(excerpt.start) ?? excerpt.text.slice(0, 40)}
                    content={quoteCitation(
                      excerpt.text,
                      name,
                      excerpt.deep_link ?? data.source_link,
                      excerpt.start,
                      excerpt.truncated,
                    )}
                  />
                ))}
              </ActionPanel.Submenu>
            ) : null}
            <Action.CopyToClipboard
              title="Copy Item ID"
              content={data.item_id}
              shortcut={{
                macOS: { modifiers: ["cmd", "shift"], key: "i" },
                Windows: { modifiers: ["ctrl", "shift"], key: "i" },
              }}
            />
          </ActionPanel>
        ) : null
      }
    />
  );
}
