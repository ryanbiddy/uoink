import { Tool } from "@raycast/api";
import { asHttpUrl, captureLabel, captureUrl } from "../lib/uoink";

type Input = {
  /**
   * The full http or https link to save: a YouTube video or playlist, X post, Reddit thread,
   * podcast feed or web article.
   */
  url: string;
};

const CORPUS_PREVIEW_CHARS = 12_000;

export const confirmation: Tool.Confirmation<Input> = async (input) => ({
  message: "Uoink this link into your library?",
  info: [{ name: "Link", value: input.url }],
});

/**
 * Save a link into the user's local Uoink library. Video captures include the timestamped transcript.
 * Can take a few minutes for long videos. Only call it when the user asks to save or uoink something.
 */
export default async function tool(input: Input) {
  const url = asHttpUrl(input.url);
  if (!url) {
    throw new Error(`Not an http or https link: ${input.url}`);
  }
  const result = await captureUrl(url);
  const corpus = result.corpus_md ?? "";
  return {
    saved: captureLabel(result),
    itemId: result.video_id ?? undefined,
    slug: result.slug,
    queued: Boolean(result.job_id),
    markdown: corpus ? corpus.slice(0, CORPUS_PREVIEW_CHARS) : undefined,
    markdownTruncated: corpus.length > CORPUS_PREVIEW_CHARS,
  };
}
