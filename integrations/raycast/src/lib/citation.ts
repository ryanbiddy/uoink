// Citation formats shared by every Uoink integration (Raycast, Obsidian, Alfred,
// Flow Launcher). No imports, so the helpers stay easy to check on their own.
//
//   saved source text   > Working memory holds about four chunks…
//   (timed_clip,        >
//    text_only)         > — [How memory works @ 4:12](https://youtu.be/abc?t=252)
//   anything else       [How memory works @ 4:12](https://youtu.be/abc?t=252)

/** The search-hit fields a citation needs. */
export interface CitableHit {
  item_id?: string;
  title: string;
  evidence_kind?: string;
  start: number | null;
  deep_link: string | null;
  source_link: string | null;
  preview: { text: string; truncated: boolean };
}

export function formatTimestamp(seconds: number | null | undefined): string | undefined {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return undefined;
  }
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** The title, plus the timestamp when there is one, linked to the moment or the source. */
export function linkCitation(title: string, link: string | null, start: number | null): string {
  const stamp = formatTimestamp(start);
  const label = stamp ? `${title} @ ${stamp}` : title;
  return link ? `[${label}](${link})` : label;
}

/** A Markdown quote with an attribution line. "…" marks text that was cut short. */
export function quoteCitation(
  text: string,
  title: string,
  link: string | null,
  start: number | null,
  truncated = false,
): string {
  const body = text.trim();
  if (!body) {
    return linkCitation(title, link, start);
  }
  const quote = `${body}${truncated ? "…" : ""}`
    .split(/\r?\n/)
    .map((line) => `> ${line}`)
    .join("\n");
  return `${quote}\n>\n> — ${linkCitation(title, link, start)}`;
}

/**
 * The preview is saved source text: a timed transcript clip or a passage from
 * the saved prose. A discovery_hint is a search snippet or the title, and a
 * missing or unknown kind is never quoted.
 */
export function isQuotable(hit: CitableHit): boolean {
  return hit.evidence_kind === "timed_clip" || hit.evidence_kind === "text_only";
}

/** Quote saved source text; otherwise cite the item and moment without quoting. */
export function hitCitation(hit: CitableHit): string {
  const title = hit.title || hit.item_id || "Untitled";
  const link = hit.deep_link ?? hit.source_link;
  return isQuotable(hit)
    ? quoteCitation(hit.preview.text, title, link, hit.start, hit.preview.truncated)
    : linkCitation(title, link, hit.start);
}
