import { App, Editor, Modal, Notice, Plugin, PluginSettingTab, Setting, SuggestModal } from "obsidian";
import {
	asHttpUrl,
	captureLabel,
	defaultCliPath,
	formatTimestamp,
	hitCitation,
	INSTALL_URL,
	itemMarkdown,
	RecentItem,
	SearchHit,
	Uoink,
	UoinkError,
} from "./uoink";

interface UoinkSettings {
	cliPath: string;
}

const DEFAULT_SETTINGS: UoinkSettings = { cliPath: "" };

type Suggestion = { kind: "hit"; hit: SearchHit } | { kind: "recent"; item: RecentItem };

const TYPING_PAUSE_MS = 200;
const NO_MATCHES = "No matches in your Uoink library.";

function errorText(error: unknown): string {
	if (error instanceof UoinkError && error.code === "cli_missing") {
		return `${error.message} Get it at ${INSTALL_URL}`;
	}
	return error instanceof Error ? error.message : String(error);
}

class LibraryModal extends SuggestModal<Suggestion> {
	private latestQuery = "";
	private lastResults: Suggestion[] = [];

	constructor(
		app: App,
		private readonly uoink: Uoink,
		private readonly onPick: (suggestion: Suggestion) => Promise<void>,
		placeholder: string,
	) {
		super(app);
		this.setPlaceholder(placeholder);
		this.emptyStateText = NO_MATCHES;
	}

	async getSuggestions(query: string): Promise<Suggestion[]> {
		const trimmed = query.trim();
		this.latestQuery = trimmed;
		try {
			if (!trimmed) {
				const recent = await this.uoink.recent();
				this.emptyStateText = NO_MATCHES;
				return recent.map((item) => ({ kind: "recent" as const, item }));
			}
			// Each search starts the CLI, so wait for a pause in typing.
			await new Promise((resolve) => window.setTimeout(resolve, TYPING_PAUSE_MS));
			if (trimmed !== this.latestQuery) {
				return this.lastResults;
			}
			const hits = await this.uoink.search(trimmed);
			// A search that works again clears an earlier error message.
			this.emptyStateText = NO_MATCHES;
			this.lastResults = hits.map((hit) => ({ kind: "hit" as const, hit }));
			return this.lastResults;
		} catch (error) {
			// Only the current query's failure replaces the empty-state text.
			if (trimmed === this.latestQuery) {
				this.emptyStateText = errorText(error);
			}
			return [];
		}
	}

	renderSuggestion(suggestion: Suggestion, el: HTMLElement) {
		if (suggestion.kind === "recent") {
			el.createDiv({ text: suggestion.item.title || suggestion.item.slug });
			el.createEl("small", { text: `Saved ${(suggestion.item.yoinked_at ?? "").slice(0, 10)}` });
			return;
		}
		const { hit } = suggestion;
		const details = [formatTimestamp(hit.start), hit.channel, hit.preview.text].filter(Boolean).join(" · ");
		el.createDiv({ text: hit.title });
		el.createEl("small", { text: details.length > 160 ? `${details.slice(0, 159)}…` : details });
	}

	onChooseSuggestion(suggestion: Suggestion) {
		this.onPick(suggestion).catch((error: unknown) => new Notice(`Uoink: ${errorText(error)}`));
	}
}

class LinkModal extends Modal {
	constructor(
		app: App,
		private readonly initial: string,
		private readonly onSubmit: (url: string) => void,
	) {
		super(app);
	}

	onOpen() {
		this.setTitle("Uoink a link");
		let value = this.initial;
		const submit = () => {
			const url = asHttpUrl(value);
			if (!url) {
				new Notice("Uoink: paste a full web link, including the protocol.");
				return;
			}
			this.close();
			this.onSubmit(url);
		};
		new Setting(this.contentEl)
			.setName("Link")
			.setDesc("A YouTube video or playlist, X post, Reddit thread, podcast feed or web page.")
			.addText((text) => {
				text.setPlaceholder("Paste a link").setValue(value).onChange((next) => (value = next));
				text.inputEl.addEventListener("keydown", (event) => {
					if (event.key === "Enter") {
						event.preventDefault();
						submit();
					}
				});
				window.setTimeout(() => text.inputEl.focus(), 0);
			});
		new Setting(this.contentEl).addButton((button) => button.setButtonText("Uoink").setCta().onClick(submit));
	}

	onClose() {
		this.contentEl.empty();
	}
}

export default class UoinkPlugin extends Plugin {
	settings: UoinkSettings = DEFAULT_SETTINGS;
	private uoink = new Uoink(() => this.settings.cliPath);

	async onload() {
		await this.loadSettings();

		this.addCommand({
			id: "insert-citation",
			name: "Insert citation from library",
			editorCallback: (editor: Editor) => {
				new LibraryModal(this.app, this.uoink, (choice) => this.insert(editor, choice), "Search your Uoink library").open();
			},
		});

		this.addCommand({
			id: "search-library",
			name: "Search library and open the moment",
			callback: () => {
				new LibraryModal(this.app, this.uoink, (choice) => this.openChoice(choice), "Search your Uoink library").open();
			},
		});

		this.addCommand({
			id: "capture-link",
			name: "Save a link to the library",
			callback: async () => {
				const selected = asHttpUrl(this.app.workspace.activeEditor?.editor?.getSelection());
				if (selected) {
					await this.capture(selected);
					return;
				}
				let clipboard = "";
				try {
					clipboard = asHttpUrl(await navigator.clipboard.readText()) ?? "";
				} catch {
					clipboard = "";
				}
				new LinkModal(this.app, clipboard, (url) => void this.capture(url)).open();
			},
		});

		this.addSettingTab(new UoinkSettingTab(this.app, this));
	}

	private async insert(editor: Editor, choice: Suggestion) {
		if (choice.kind === "hit") {
			editor.replaceSelection(`${hitCitation(choice.hit)}\n`);
			return;
		}
		const item = await this.uoink.item({ slug: choice.item.slug });
		editor.replaceSelection(`${itemMarkdown(item)}\n`);
	}

	private async openChoice(choice: Suggestion) {
		const link =
			choice.kind === "hit"
				? (choice.hit.deep_link ?? choice.hit.source_link)
				: (await this.uoink.item({ slug: choice.item.slug })).source_link;
		if (link) {
			window.open(link);
		} else {
			new Notice("Uoink: this item has no web link to open.");
		}
	}

	private async capture(url: string) {
		const progress = new Notice(`Uoinking ${url}…`, 0);
		try {
			const result = await this.uoink.capture(url);
			progress.hide();
			new Notice(result.job_id ? `Queued in Uoink: ${captureLabel(result)}` : `Uoinked ${captureLabel(result)}`);
		} catch (error) {
			progress.hide();
			new Notice(`Couldn't uoink that link: ${errorText(error)}`, 10_000);
		}
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, (await this.loadData()) as Partial<UoinkSettings> | null);
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}
}

class UoinkSettingTab extends PluginSettingTab {
	constructor(
		app: App,
		private readonly plugin: UoinkPlugin,
	) {
		super(app, plugin);
	}

	display(): void {
		const { containerEl } = this;
		containerEl.empty();
		new Setting(containerEl)
			.setName("Uoink command")
			.setDesc(
				"Leave empty for a default install. Otherwise enter Uoink.app, its Contents/Helpers/uoink command, or cli\\uoink.cmd in your Uoink folder.",
			)
			.addText((text) =>
				text
					.setPlaceholder(defaultCliPath())
					.setValue(this.plugin.settings.cliPath)
					.onChange(async (value) => {
						this.plugin.settings.cliPath = value.trim();
						await this.plugin.saveSettings();
					}),
			);
	}
}
