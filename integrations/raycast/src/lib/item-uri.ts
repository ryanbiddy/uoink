// AI Chat mentions carry these URIs; read-item resolves them through the CLI.
const PREFIX = "uoink-raycast://";

export function itemUri(selector: { itemId: string } | { slug: string }): string {
  return "slug" in selector
    ? `${PREFIX}slug/${encodeURIComponent(selector.slug)}`
    : `${PREFIX}item/${encodeURIComponent(selector.itemId)}`;
}

export function parseItemUri(uri: string): { itemId: string } | { slug: string } {
  const match = /^uoink-raycast:\/\/(item|slug)\/(.+)$/.exec(uri.trim());
  if (!match) {
    throw new Error(`Not a Uoink item: ${uri}`);
  }
  const value = decodeURIComponent(match[2]);
  return match[1] === "slug" ? { slug: value } : { itemId: value };
}
