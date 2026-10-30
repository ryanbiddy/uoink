import { formatTimestamp, getItemByIdOrSlug } from "../lib/uoink";

type Input = {
  /**
   * The itemId from search-library, or the slug from list-recent-uoinks.
   */
  id: string;
};

/**
 * Open one saved item: its title, source, and a spread of excerpts with timestamps and links.
 * Use it after search-library or list-recent-uoinks when the user wants more than one passage.
 */
export default async function tool(input: Input) {
  const item = await getItemByIdOrSlug(input.id.trim());
  const { card } = item;
  return {
    itemId: item.item_id,
    title: card.title,
    from: card.channel ?? undefined,
    platform: card.platform ?? undefined,
    saved: card.yoinked_at ?? undefined,
    source: item.source_link ?? undefined,
    summary: card.summary_hint ?? undefined,
    excerpts: (card.excerpts ?? []).map((excerpt) => ({
      timestamp: formatTimestamp(excerpt.start),
      link: excerpt.deep_link ?? undefined,
      text: excerpt.text,
      truncated: excerpt.truncated,
    })),
  };
}
