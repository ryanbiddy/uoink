import { getPreferenceValues } from "@raycast/api";
import { execFile } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { formatTimestamp } from "./citation";

export { formatTimestamp, hitCitation, isVerifiedPassage, linkCitation, quoteCitation } from "./citation";

// The uoink CLI prints one JSON envelope on stdout. Failures exit 1 with
// {"ok": false, "error": ...}; usage errors exit 2 with "uoink: ..." on stderr.

export interface Preview {
  text: string;
  truncated: boolean;
}

export interface SearchHit {
  item_id: string;
  slug: string | null;
  title: string;
  channel: string;
  source_link: string | null;
  evidence_kind: "timed_clip" | "text_only" | "discovery_hint";
  timing: string | null;
  start: number | null;
  end: number | null;
  deep_link: string | null;
  preview: Preview;
  passage_verified?: boolean;
}

export interface SearchResult {
  hits: SearchHit[];
  hit_count: number;
  library_items: number;
  search_mode: string;
  fallback_reason?: string | null;
}

export interface RecentItem {
  slug: string;
  title: string | null;
  folder: string | null;
  yoinked_at: string | null;
}

export interface Excerpt {
  excerpt_id: string;
  evidence_kind: string;
  start: number | null;
  end: number | null;
  timing: string | null;
  text: string;
  deep_link: string | null;
  truncated: boolean;
}

export interface Card {
  video_id: string;
  slug: string | null;
  title: string | null;
  channel: string | null;
  platform: string | null;
  source_type: string | null;
  topic: string | null;
  yoinked_at: string | null;
  url: string | null;
  summary_hint?: string | null;
  clip_count?: number;
  excerpts?: Excerpt[];
}

export interface LibraryItem {
  item_id: string;
  card: Card;
  source_link: string | null;
}

export interface CaptureResult {
  video_id?: string | null;
  slug?: string;
  title?: string;
  folder?: string;
  corpus_md?: string;
  job_id?: string;
  feed?: { title?: string };
  metadata?: { title?: string };
}

export interface NoteResult {
  video_id: string;
  slug: string;
  title: string;
}

export interface Status {
  version: string;
  data_dir: string;
  helper_running: boolean;
}

export class UoinkError extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message);
    this.name = "UoinkError";
  }
}

/** The CLI could not be found or launched. Commands offer install help for this one. */
export class UoinkMissingError extends UoinkError {
  constructor(message: string) {
    super(message, "cli_missing");
    this.name = "UoinkMissingError";
  }
}

export const INSTALL_URL = "https://uoink.app/install";

interface Launcher {
  file: string;
  prefix: string[];
}

function defaultCandidates(): string[] {
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA ?? path.join(homedir(), "AppData", "Local");
    return [path.join(local, "Uoink", "cli", "uoink.cmd")];
  }
  return [
    "/Applications/Uoink.app/Contents/Helpers/uoink",
    path.join(homedir(), "Applications", "Uoink.app", "Contents", "Helpers", "uoink"),
  ];
}

function isFile(candidate: string): boolean {
  try {
    return statSync(candidate).isFile();
  } catch {
    return false;
  }
}

/**
 * Map a configured or default path to an executable and its fixed arguments.
 * Windows .cmd shims would need cmd.exe, which re-parses arguments, so run the
 * bundled Python against uoink_cli.py directly, as the shim itself does.
 */
function launcherFor(candidate: string): Launcher | undefined {
  let target = candidate;
  if (target.endsWith(".app")) {
    target = path.join(target, "Contents", "Helpers", "uoink");
  }
  if (!isFile(target)) {
    return undefined;
  }
  if (/\.(cmd|bat)$/i.test(target)) {
    const root = path.dirname(path.dirname(target));
    const python = path.join(root, "python", "python.exe");
    const script = path.join(root, "uoink_cli.py");
    return existsSync(python) && existsSync(script) ? { file: python, prefix: [script] } : undefined;
  }
  return { file: target, prefix: [] };
}

export function resolveLauncher(): Launcher {
  const { cliPath } = getPreferenceValues<Preferences>();
  const configured = cliPath?.trim();
  const candidates = configured ? [configured] : defaultCandidates();
  for (const candidate of candidates) {
    const launcher = launcherFor(candidate);
    if (launcher) {
      return launcher;
    }
  }
  throw new UoinkMissingError(
    configured
      ? `No Uoink CLI at ${configured}. Choose the uoink command in the extension preferences.`
      : "Uoink isn't installed in its default location. Install it, or set the CLI path in the extension preferences.",
  );
}

function stderrMessage(stderr: string): string | undefined {
  const lines = stderr
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const usage = lines.find((line) => line.startsWith("uoink: "));
  return usage ? usage.slice("uoink: ".length) : lines.at(-1);
}

function errorFromPayload(payload: { error?: unknown }): UoinkError {
  const error = payload.error;
  if (error && typeof error === "object") {
    const { code, message } = error as { code?: string; message?: string };
    return new UoinkError(message ?? code ?? "Uoink couldn't finish that.", code);
  }
  return new UoinkError(typeof error === "string" && error ? error : "Uoink couldn't finish that.");
}

export interface RunOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

/** Run one uoink CLI command and return its successful JSON payload. */
export async function runUoink<T>(args: string[], options: RunOptions = {}): Promise<T> {
  // Async, so a missing CLI rejects like any other failure instead of throwing during render.
  const launcher = resolveLauncher();
  return new Promise<T>((resolve, reject) => {
    execFile(
      launcher.file,
      [...launcher.prefix, ...args],
      {
        env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
        timeout: options.timeoutMs ?? 60_000,
        signal: options.signal,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        if (error?.name === "AbortError") {
          reject(error);
          return;
        }
        let payload: ({ ok?: boolean } & T) | undefined;
        try {
          payload = stdout.trim() ? JSON.parse(stdout) : undefined;
        } catch {
          payload = undefined;
        }
        if (payload?.ok === true) {
          resolve(payload);
        } else if (payload) {
          reject(errorFromPayload(payload as { error?: unknown }));
        } else if (error && "code" in error && error.code === "ENOENT") {
          reject(new UoinkMissingError(`Couldn't start ${launcher.file}. Reinstall Uoink or update the CLI path.`));
        } else if (error?.killed) {
          reject(new UoinkError("Uoink took too long to answer. Try again, or check the Uoink app.", "timeout"));
        } else {
          reject(new UoinkError(stderrMessage(stderr) ?? error?.message ?? "Uoink returned no result."));
        }
      },
    );
  });
}

// Options go first and "--" ends option parsing, so text that starts with "-"
// (a query like "-v", a note like "-idea") stays a positional argument.
export function searchLibrary(query: string, limit = 10, options?: RunOptions) {
  return runUoink<SearchResult>(["search", "--limit", String(limit), "--", query], options);
}

export async function listRecent(limit = 20, options?: RunOptions): Promise<RecentItem[]> {
  const result = await runUoink<{ yoinks: RecentItem[] }>(["recent", "--limit", String(limit)], options);
  return result.yoinks;
}

export function getItem(selector: { itemId: string } | { slug: string }, options?: RunOptions) {
  const args = "slug" in selector ? ["get", "--slug", "--", selector.slug] : ["get", "--", selector.itemId];
  return runUoink<LibraryItem>(args, options);
}

/** Item IDs and slugs both come back from search and recent; accept either. */
export async function getItemByIdOrSlug(id: string, options?: RunOptions): Promise<LibraryItem> {
  try {
    return await getItem({ itemId: id }, options);
  } catch (error) {
    if (error instanceof UoinkError && error.code === "resource_not_found") {
      return getItem({ slug: id }, options);
    }
    throw error;
  }
}

// Long videos run transcription and screenshots before the CLI returns.
const CAPTURE_TIMEOUT_MS = 30 * 60_000;

export function captureUrl(url: string) {
  return runUoink<CaptureResult>(["capture", "--", url], { timeoutMs: CAPTURE_TIMEOUT_MS });
}

export function saveNote(text: string, title?: string) {
  // --title=value keeps a title that starts with "-" attached to its flag.
  return runUoink<NoteResult>(["note", ...(title ? [`--title=${title}`] : []), "--", text]);
}

export function getStatus() {
  return runUoink<Status>(["status"]);
}

export function captureLabel(result: CaptureResult): string {
  return (
    result.title ?? result.metadata?.title ?? result.feed?.title ?? result.slug ?? result.video_id ?? "your library"
  );
}

export function asHttpUrl(text: string | undefined): string | undefined {
  const candidate = text?.trim();
  if (!candidate || /\s/.test(candidate)) {
    return undefined;
  }
  try {
    const url = new URL(candidate);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

/** The whole card as Markdown, for the detail view, AI mentions and copying. */
export function itemMarkdown(item: LibraryItem): string {
  const { card } = item;
  const title = card.title || card.slug || item.item_id;
  const facts = [
    card.channel && `**From:** ${card.channel}`,
    card.platform && `**Platform:** ${card.platform}`,
    card.yoinked_at && `**Saved:** ${card.yoinked_at.slice(0, 10)}`,
    item.source_link && `**Source:** ${item.source_link}`,
  ].filter(Boolean);
  const excerpts = (card.excerpts ?? []).map((excerpt) => {
    const stamp = formatTimestamp(excerpt.start);
    const heading = stamp ? (excerpt.deep_link ? `[${stamp}](${excerpt.deep_link})` : stamp) : "Excerpt";
    return `### ${heading}\n\n${excerpt.text.trim()}${excerpt.truncated ? "…" : ""}`;
  });
  return [
    `# ${title}`,
    facts.join("  \n"),
    excerpts.length ? excerpts.join("\n\n") : (card.summary_hint ?? "This item has no excerpts yet."),
  ]
    .filter(Boolean)
    .join("\n\n");
}
