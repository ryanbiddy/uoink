import { listRecent } from "../lib/uoink";

type Input = {
  /**
   * How many items to return, from 1 to 50. Defaults to 10.
   */
  limit?: number;
};

/**
 * List the newest items the user saved to Uoink, newest first.
 */
export default async function tool(input: Input) {
  const limit = Math.min(50, Math.max(1, Math.round(input.limit ?? 10)));
  const items = await listRecent(limit);
  return items.map((item) => ({
    slug: item.slug,
    title: item.title ?? item.slug,
    saved: item.yoinked_at ?? undefined,
  }));
}
