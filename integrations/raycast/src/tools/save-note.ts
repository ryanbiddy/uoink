import { Tool } from "@raycast/api";
import { saveNote } from "../lib/uoink";

type Input = {
  /**
   * The note text, exactly as the user wants it saved.
   */
  text: string;
  /**
   * An optional short title. Uoink derives one from the text when it is missing.
   */
  title?: string;
};

export const confirmation: Tool.Confirmation<Input> = async (input) => ({
  message: "Save this note to your Uoink library?",
  info: [
    { name: "Title", value: input.title },
    { name: "Note", value: input.text.length > 280 ? `${input.text.slice(0, 280)}…` : input.text },
  ],
});

/**
 * Save text as a searchable note in the user's local Uoink library.
 */
export default async function tool(input: Input) {
  const note = await saveNote(input.text, input.title?.trim() || undefined);
  return { itemId: note.video_id, slug: note.slug, title: note.title };
}
