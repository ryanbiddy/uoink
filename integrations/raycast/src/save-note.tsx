import { Action, ActionPanel, Form, Icon, popToRoot, showHUD, showToast, Toast } from "@raycast/api";
import { FormValidation, useForm } from "@raycast/utils";
import { showUoinkFailure } from "./lib/feedback";
import { saveNote } from "./lib/uoink";

interface NoteValues {
  title: string;
  text: string;
}

export default function SaveNote() {
  const { handleSubmit, itemProps } = useForm<NoteValues>({
    async onSubmit(values) {
      const toast = await showToast({ style: Toast.Style.Animated, title: "Saving note…" });
      try {
        const note = await saveNote(values.text, values.title.trim() || undefined);
        await toast.hide();
        await showHUD(`Saved “${note.title}” to Uoink`);
        await popToRoot({ clearSearchBar: true });
      } catch (error) {
        await toast.hide();
        await showUoinkFailure(error, "Couldn't save the note");
      }
    },
    validation: { text: FormValidation.Required },
  });

  return (
    <Form
      enableDrafts
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Save Note" icon={Icon.SaveDocument} onSubmit={handleSubmit} />
        </ActionPanel>
      }
    >
      <Form.TextField title="Title" placeholder="Optional. Uoink derives one from the text" {...itemProps.title} />
      <Form.TextArea title="Note" placeholder="An idea, a quote, a hook to try…" {...itemProps.text} />
    </Form>
  );
}
