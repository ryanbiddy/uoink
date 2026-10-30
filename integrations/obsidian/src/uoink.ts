import { execFile } from "child_process";
import { existsSync, statSync } from "fs";
import { homedir } from "os";
import * as path from "path";

// The uoink CLI prints one JSON envelope on stdout. Failures exit 1 with
// {"ok": false, "error": ...}; usage errors exit 2 with "uoink: ..." on stderr.

export interface SearchHit {
	item_id: string;
	title: string;
	channel: string;
	source_link: string | null;
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

export function defaultCliPath(): string {
	if (process.platform === "win32") {
		const local = process.env.LOCALAPPDATA ?? path.join(homedir(), "AppData", "Local");
		return path.join(local, "Uoink", "cli", "uoink.cmd");
	}
	return "/Applications/Uoink.app/Contents/Helpers/uoink";
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

	async search(query: string, limit = 15): Promise<SearchHit[]> {
		const result = await this.run<{ hits: SearchHit[] }>(["search", query, "--limit", String(limit)]);
		return result.hits;
	}

	async recent(limit = 15): Promise<RecentItem[]> {
		const result = await this.run<{ yoinks: RecentItem[] }>(["recent", "--limit", String(limit)]);
		return result.yoinks;
	}

	item(selector: { itemId: string } | { slug: string }): Promise<LibraryItem> {
		return this.run<LibraryItem>("slug" in selector ? ["get", selector.slug, "--slug"] : ["get", selector.itemId]);
	}

	capture(url: string): Promise<CaptureResult> {
		// Long videos transcribe and take screenshots before the CLI returns.
		return this.run<CaptureResult>(["capture", url], 30 * 60_000);
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

/** A Markdown quote that links back to the moment, or to the source when untimed. */
export function citation(text: string, title: string, link: string | null, start: number | null): string {
	const stamp = formatTimestamp(start);
	const label = stamp ? `${title} @ ${stamp}` : title;
	const quote = text
		.trim()
		.split(/\r?\n/)
		.map((line) => `> ${line}`)
		.join("\n");
	return `${quote}\n>\n> — ${link ? `[${label}](${link})` : label}`;
}

export function hitCitation(hit: SearchHit): string {
	return citation(hit.preview.text || hit.title, hit.title, hit.deep_link ?? hit.source_link, hit.start);
}

/** An item's card as Markdown: title, source and timestamped excerpts. */
export function itemMarkdown(item: LibraryItem): string {
	const title = item.card.title || item.card.slug || item.item_id;
	const heading = item.source_link ? `## [${title}](${item.source_link})` : `## ${title}`;
	const excerpts = (item.card.excerpts ?? []).map((excerpt) =>
		citation(excerpt.text + (excerpt.truncated ? " …" : ""), title, excerpt.deep_link ?? item.source_link, excerpt.start),
	);
	return [heading, ...(excerpts.length ? excerpts : [item.card.summary_hint ?? ""])].filter(Boolean).join("\n\n");
}
