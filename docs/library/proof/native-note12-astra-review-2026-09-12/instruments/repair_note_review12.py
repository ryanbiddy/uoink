"""Apply the documented integrator corrections in the worker tree only."""
from pathlib import Path
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d8840cdd-c3a\gemini')
p=w/'notes.py';s=p.read_text(encoding='utf8')
anchor='def persist_note(idx, note: dict, *, data_root: Path | None = None,'
helper='''def compute_note_health(sidecar: dict) -> dict:
    """Check actual note text; type tags and fixture markers are not content."""
    def has_text(value):
        return isinstance(value, str) and bool(value.strip())

    present = any(has_text(sidecar.get(key)) for key in
                  ("note", "text", "markdown", "body", "transcript"))
    transcript = sidecar.get("transcript")
    if isinstance(transcript, list):
        present = present or any(isinstance(segment, dict) and
                                 has_text(segment.get("text"))
                                 for segment in transcript)
    return {
        "transcript": "ok" if present else "missing",
        "screenshots": "skipped",
        "comments": "skipped",
        "hook": "skipped",
        "comment_intelligence": "skipped",
    }


'''
assert s.count(anchor)==1;s=s.replace(anchor,helper+anchor)
block='''health = {
            "transcript": "ok" if md else "missing",
            "screenshots": "skipped",
            "comments": "skipped",
            "hook": "skipped",
            "comment_intelligence": "skipped",
        }'''
assert block in s;s=s.replace('        '+block+'\n','')
block2='''    health = {
        "transcript": "ok" if md else "missing",
        "screenshots": "skipped",
        "comments": "skipped",
        "hook": "skipped",
        "comment_intelligence": "skipped",
    }

'''
assert block2 in s;s=s.replace(block2,'')
s=s.replace('    corpus_path = None\n','    health = compute_note_health({"note": md})\n    corpus_path = None\n')
p.write_text(s,encoding='utf8',newline='\n')
p=w/'server.py';s=p.read_text(encoding='utf8')
start=s.index('    source_type = str(sidecar.get("source_type")',s.index('def compute_health('))
end=s.index('\n\n',s.index('        "comment_intelligence":',start))
old=s[start:end]
new='''    source_type = str(sidecar.get("source_type") or "").strip().lower()
    platform = str(sidecar.get("platform") or "").strip().lower()
    if source_type == "note" or platform == "note":
        return notes.compute_note_health(sidecar)

    comments = sidecar.get("comments")
    comments_status = sidecar.get("comments_status") or "unknown"
    if isinstance(comments, list) and len(comments) >= 5:
        comments_health = "ok"
    elif isinstance(comments, list) and len(comments) > 0:
        comments_health = "ok -- fewer than 5 comments"
    elif comments_status == "pending":
        comments_health = "pending"
    else:
        comments_health = "missing"
    return {
        "transcript": "ok" if sidecar.get("transcript") else "missing",
        "screenshots": "ok" if sidecar.get("screenshots") else "missing",
        "comments": comments_health,
        "hook": sidecar.get("hook_type_status") or "skipped",
        "comment_intelligence": sidecar.get("comment_intelligence_status") or "skipped",
    }'''
s=s[:start]+new+s[end:];p.write_text(s,encoding='utf8',newline='\n')
p=w/'assets/dashboard/index.html';s=p.read_text(encoding='utf8')
anchor='    function yoinkFactsHtml(row, sidecar = {}) {'
helper='''    function noteReadinessLabel() {
      if (state.selectedYoinkMarkdown) return "ready";
      if (state.selectedYoinkMarkdownState === "loading") return "checking";
      if (state.selectedYoinkMarkdownState === "empty") return "empty";
      return state.selectedYoinkMarkdownError || "unavailable";
    }

'''
assert s.count(anchor)==1;s=s.replace(anchor,helper+anchor)
old='      const markdownState = state.selectedYoinkMarkdown\n'
assert s.count(old)==1;s=s.replace(old,'      const markdownState = isNote ? noteReadinessLabel() : state.selectedYoinkMarkdown\n')
s=s.replace('facts.push(["Saved details", "ready"]);','facts.push(["Saved details", noteReadinessLabel()]);')
old='els.yoinkFactMeta.textContent = (isNote || state.selectedYoinkSidecar) ? "ready" : "checking saved files";'
assert old in s;s=s.replace(old,'els.yoinkFactMeta.textContent = isNote ? noteReadinessLabel() : (state.selectedYoinkSidecar ? "ready" : "checking saved files");')
p.write_text(s,encoding='utf8',newline='\n')
print('Applied note content and readiness corrections; no test edits.')
