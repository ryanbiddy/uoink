import { listRecent, searchLibrary } from "../lib/uoink";
import { itemUri } from "../lib/item-uri";

type Input = {
  /** What the user typed after choosing the search, empty for the default list. */
  query: string;
};

type Item = {
  title: string;
  uri?: string;
  description?: string;
};

/** Offers saved items in the AI Chat @ menu; read-item supplies their content. */
export default async function tool(input: Input): Promise<Item[]> {
  const query = input.query.trim();
  if (!query) {
    const recent = await listRecent(20);
    return recent.map((item) => ({ title: item.title || item.slug, uri: itemUri({ slug: item.slug }) }));
  }
  const result = await searchLibrary(query, 20);
  const seen = new Set<string>();
  const items: Item[] = [];
  for (const hit of result.hits) {
    if (seen.has(hit.item_id)) {
      continue;
    }
    seen.add(hit.item_id);
    items.push({ title: hit.title, uri: itemUri({ itemId: hit.item_id }), description: hit.channel || undefined });
  }
  return items;
}
