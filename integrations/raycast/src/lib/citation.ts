// Citation formats shared by every Uoink integration (Raycast, Obsidian, Alfred,
// Flow Launcher). No imports, so the helpers stay easy to check on their own.
//
//   verified passage   > Working memory holds about four chunks…
//                      >
//                      > — [How memory works @ 4:12](https://youtu.be/abc?t=252)
//   anything else      [How memory works @ 4:12](https://youtu.be/abc?t=252)

/** The search-hit fields a citation needs. */
export interface CitableHit {
  item_id?: string;
  title: string;
  evidence_kind?: string;
  passage_verified?: boolean;
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

/** Uoink found this exact text in the saved source. Title and metadata matches never are. */
export function isVerifiedPassage(hit: CitableHit): boolean {
  return hit.passage_verified === true && hit.evidence_kind !== "discovery_hint";
}

/** Quote a verified passage; otherwise cite the item and moment without quoting. */
export function hitCitation(hit: CitableHit): string {
  const title = hit.title || hit.item_id || "Untitled";
  const link = hit.deep_link ?? hit.source_link;
  return isVerifiedPassage(hit)
    ? quoteCitation(hit.preview.text, title, link, hit.start, hit.preview.truncated)
    : linkCitation(title, link, hit.start);
}
