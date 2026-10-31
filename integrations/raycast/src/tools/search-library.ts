import { formatTimestamp, isVerifiedPassage, searchLibrary } from "../lib/uoink";

type Input = {
  /**
   * Key words to look for in the user's saved videos, podcasts, articles, threads and notes.
   * Use the distinctive words of the topic, not a full question.
   */
  query: string;
  /**
   * How many results to return, from 1 to 20. Defaults to 8.
   */
  limit?: number;
};

/**
 * Search the user's local Uoink library. Returns matching passages with the item they came from,
 * a timestamp when the passage is timed, and a link that opens the source at that moment.
 */
export default async function tool(input: Input) {
  const limit = Math.min(20, Math.max(1, Math.round(input.limit ?? 8)));
  const result = await searchLibrary(input.query, limit);
  return {
    libraryItems: result.library_items,
    results: result.hits.map((hit) => ({
      itemId: hit.item_id,
      title: hit.title,
      from: hit.channel || undefined,
      timestamp: formatTimestamp(hit.start),
      link: hit.deep_link ?? hit.source_link ?? undefined,
      passage: hit.preview.text,
      passageVerified: isVerifiedPassage(hit),
      passageTruncated: hit.preview.truncated,
      match: hit.evidence_kind,
    })),
  };
}
