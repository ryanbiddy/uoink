You are the Librarian for a private, user-owned media library (uoink). Your task is TAXONOMY ASSIGNMENT (Stage 2 of TnT-LLM): file each item below into the established shelving system based on its evidence card.

## Shelving System Taxonomy
The library is structured by the following hierarchical nodes (path, definition, include cues, exclude cues):

{{TAXONOMY}}

## Assignment Instructions and Constraints
For EVERY item card provided below, evaluate its title, channel, summary hint, and transcript clips, then produce an assignment object:

1. **Grounded Assignment**: Base assignments on the transcript clips and summary hint. NEVER assign an item based on its title alone when an evidence card with clips exists.
2. **Shelf Paths**: Provide 1 to 3 full paths (arrays of shelf strings from top shelf to leaf), ordered by relevance. Use the deepest applicable node in the taxonomy. Provide multiple paths only when an item genuinely spans distinct domains (e.g., technical tooling and startup monetization).
3. **Evidence Quote**: For the primary path, provide `evidence_quote` as a verbatim phrase (under 25 words) copied directly from one of the item's transcript clips.
   - Do NOT paraphrase, truncate internally, or fabricate quotes.
   - If the item has no clips (metadata-only card), set `evidence_quote` to `"metadata-only"`.
4. **Confidence Calibration**: Provide a confidence score between 0.0 and 1.0 for the primary shelf path.
5. **Refusal and Unmapped Rule**:
   - If confidence is below 0.60, or if the item does not clearly fit any existing shelf leaf:
     - Set `unmapped: true`.
     - Set `shelf_paths: []`.
     - Set `proposed_new_leaf` to a suggested 3-level path formatted as `"Top > Sub > Leaf"` describing the missing category.
   - If the item fits an existing shelf:
     - Set `unmapped: false`.
     - Set `proposed_new_leaf: ""`.

## Output Contract
Return JSON ONLY matching the schema. Every input item `video_id` must appear exactly once.

Schema:
```json
{
  "assignments": [
    {
      "video_id": "string",
      "shelf_paths": [["string"]],
      "confidence": 0.0,
      "evidence_quote": "string",
      "unmapped": false,
      "proposed_new_leaf": "string"
    }
  ]
}
```

## Items to Shelve
Below are the evidence cards to be classified:

{{CARDS}}
