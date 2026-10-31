import { execFile } from "child_process";
import { existsSync, statSync } from "fs";
import { homedir } from "os";
import * as path from "path";
import { quoteCitation } from "./citation";

export { formatTimestamp, hitCitation, isQuotable, linkCitation, quoteCitation } from "./citation";

// The uoink CLI prints one JSON envelope on stdout. Failures exit 1 with
// {"ok": false, "error": ...}; usage errors exit 2 with "uoink: ..." on stderr.

export interface SearchHit {
	item_id: string;
	title: string;
	channel: string;
	source_link: string | null;
	evidence_kind: "timed_clip" | "text_only" | "discovery_hint";
	start: number | null;
	deep_link: string | null;
	preview: { text: string; truncated: boolean };
}

export interface RecentItem {
	slug: string;
	title: string | null;
	yoinked_at: string | null;
}

export interface Excerpt {
	excerpt_id: string;
	start: number | null;
	text: string;
	deep_link: string | null;
	truncated: boolean;
}

export interface LibraryItem {
	item_id: string;
	source_link: string | null;
	card: {
		title: string | null;
		slug: string | null;
		channel: string | null;
		summary_hint?: string | null;
		excerpts?: Excerpt[];
	};
}

export interface CaptureResult {
	slug?: string;
	title?: string;
	video_id?: string | null;
	job_id?: string;
	metadata?: { title?: string };
	feed?: { title?: string };
}

export class UoinkError extends Error {
	constructor(message: string, readonly code?: string) {
		super(message);
		this.name = "UoinkError";
	}
}

export const INSTALL_URL = "https://uoink.app/install";

interface Launcher {
	file: string;
	prefix: string[];
}

function defaultCliCandidates(): [string, ...string[]] {
	if (process.platform === "win32") {
		const local = process.env.LOCALAPPDATA ?? path.join(homedir(), "AppData", "Local");
		return [path.join(local, "Uoink", "cli", "uoink.cmd")];
	}
	return [
		"/Applications/Uoink.app/Contents/Helpers/uoink",
		path.join(homedir(), "Applications", "Uoink.app", "Contents", "Helpers", "uoink"),
	];
}

/** The first default location that exists, else the standard one (named in errors). */
export function defaultCliPath(): string {
	const candidates = defaultCliCandidates();
	return candidates.find(isFile) ?? candidates[0];
}

function isFile(candidate: string): boolean {
	try {
		return statSync(candidate).isFile();
	} catch {
		return false;
	}
}

/**
 * Map the configured path to an executable plus fixed arguments. A Windows
 * .cmd shim would need cmd.exe, which re-parses arguments, so run the bundled
 * Python against uoink_cli.py directly, as the shim itself does.
 */
function launcherFor(configured: string): Launcher {
	let target = configured.trim() || defaultCliPath();
	if (target.endsWith(".app")) {
		target = path.join(target, "Contents", "Helpers", "uoink");
	}
	if (isFile(target) && /\.(cmd|bat)$/i.test(target)) {
		const root = path.dirname(path.dirname(target));
		const python = path.join(root, "python", "python.exe");
		const script = path.join(root, "uoink_cli.py");
		if (existsSync(python) && existsSync(script)) {
			return { file: python, prefix: [script] };
		}
	} else if (isFile(target)) {
		return { file: target, prefix: [] };
	}
	throw new UoinkError(`No Uoink CLI at ${target}. Install Uoink or set its path in this plugin's options.`, "cli_missing");
}

function stderrMessage(stderr: string): string | undefined {
	const lines = stderr
		.split(/\r?\n/)
		.map((line) => line.trim())
		.filter(Boolean);
	const usage = lines.find((line) => line.startsWith("uoink: "));
	return usage ? usage.slice("uoink: ".length) : lines[lines.length - 1];
}

export class Uoink {
	constructor(private readonly cliPath: () => string) {}

	async run<T>(args: string[], timeoutMs = 60_000): Promise<T> {
		const launcher = launcherFor(this.cliPath());
		return new Promise<T>((resolve, reject) => {
			execFile(
				launcher.file,
				[...launcher.prefix, ...args],
				{
					env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
					encoding: "utf8",
					maxBuffer: 64 * 1024 * 1024,
					timeout: timeoutMs,
					windowsHide: true,
				},
				(error, stdout, stderr) => {
					let payload: { ok?: boolean; error?: unknown } | undefined;
					try {
						payload = stdout.trim() ? (JSON.parse(stdout) as { ok?: boolean; error?: unknown }) : undefined;
					} catch {
						payload = undefined;
					}
					if (payload?.ok === true) {
						resolve(payload as T);
						return;
					}
					if (payload) {
						const err = payload.error as { code?: string; message?: string } | string | undefined;
						reject(
							typeof err === "object" && err
								? new UoinkError(err.message ?? err.code ?? "Uoink couldn't finish that.", err.code)
								: new UoinkError(typeof err === "string" && err ? err : "Uoink couldn't finish that."),
						);
						return;
					}
					if (error?.killed) {
						reject(new UoinkError("Uoink took too long to answer.", "timeout"));
						return;
					}
					reject(new UoinkError(stderrMessage(stderr) ?? error?.message ?? "Uoink returned no result."));
				},
			);
		});
	}

	// Options go first and "--" ends option parsing, so text that starts with
	// "-" stays a positional argument.
	async search(query: string, limit = 15): Promise<SearchHit[]> {
		const result = await this.run<{ hits: SearchHit[] }>(["search", "--limit", String(limit), "--", query]);
		return result.hits;
	}

	async recent(limit = 15): Promise<RecentItem[]> {
		const result = await this.run<{ yoinks: RecentItem[] }>(["recent", "--limit", String(limit)]);
		return result.yoinks;
	}

	item(selector: { itemId: string } | { slug: string }): Promise<LibraryItem> {
		return this.run<LibraryItem>(
			"slug" in selector ? ["get", "--slug", "--", selector.slug] : ["get", "--", selector.itemId],
		);
	}

	capture(url: string): Promise<CaptureResult> {
		// Long videos transcribe and take screenshots before the CLI returns.
		return this.run<CaptureResult>(["capture", "--", url], 30 * 60_000);
	}
}

export function captureLabel(result: CaptureResult): string {
	return result.title ?? result.metadata?.title ?? result.feed?.title ?? result.slug ?? "your library";
}

export function asHttpUrl(text: string | undefined | null): string | undefined {
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

/** An item's card as Markdown: title, source and timestamped excerpts. */
export function itemMarkdown(item: LibraryItem): string {
	const title = item.card.title || item.card.slug || item.item_id;
	const heading = item.source_link ? `## [${title}](${item.source_link})` : `## ${title}`;
	// Card excerpts are stored text from the item itself, so they are quoted.
	const excerpts = (item.card.excerpts ?? []).map((excerpt) =>
		quoteCitation(excerpt.text, title, excerpt.deep_link ?? item.source_link, excerpt.start, excerpt.truncated),
	);
	return [heading, ...(excerpts.length ? excerpts : [item.card.summary_hint ?? ""])].filter(Boolean).join("\n\n");
}
