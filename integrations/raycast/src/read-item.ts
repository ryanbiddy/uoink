import { parseItemUri } from "./lib/item-uri";
import { getItem, itemMarkdown } from "./lib/uoink";

type Input = {
  /** The `uri` of an item mention-library returned. */
  uri: string;
};

/** Resource provider: the Markdown card for an item mentioned in AI Chat. */
export default async function readItem(input: Input): Promise<string> {
  return itemMarkdown(await getItem(parseItemUri(input.uri)));
}
