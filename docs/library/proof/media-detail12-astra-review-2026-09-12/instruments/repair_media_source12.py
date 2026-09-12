import difflib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
out=r/'_scratch/media-detail12-review'
def change(text,old,new,count=1):
    assert text.count(old)==count,(old[:100],text.count(old))
    return text.replace(old,new)
p=w/'server.py';old=p.read_text(encoding='utf8');s=old
s=change(s,'            cur = p\n            while True:\n', '''            # Lexical containment must precede metadata probes on this path.
            p.relative_to(DESKTOP_ROOT.absolute())
            cur = p
            while True:
''')
s=change(s,'            with open(resolved, "r", encoding="utf-8") as f:\n                content = f.read(MAX_SIDECAR_BYTES + 1)', '            with open(resolved, "rb") as f:\n                content = f.read(MAX_SIDECAR_BYTES + 1)')
s=change(s,'        try:\n            data = json.loads(content)\n        except (ValueError, TypeError):', '''        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("non-finite JSON number")
            return number

        def reject_constant(value):
            raise ValueError("non-finite JSON constant")

        try:
            data = json.loads(content.decode("utf-8"), parse_float=finite_float,
                              parse_constant=reject_constant)
        except (ValueError, TypeError, RecursionError):''')
start=s.index('        raw_speakers = data.get("speakers")',s.index('    def _handle_yoink_details'))
end=s.index('            if "segments" in raw_diar',start)
s=s[:start]+'''        def clean_speakers(raw):
            def label_fields(speaker):
                return {key: speaker[key] for key in ("name", "label", "id")
                        if isinstance(speaker.get(key), str) and speaker[key].strip()}
            if isinstance(raw, list):
                return [clean for speaker in raw
                        if (clean := speaker if isinstance(speaker, str)
                            else label_fields(speaker) if isinstance(speaker, dict)
                            else None)]
            if isinstance(raw, dict):
                # Map keys are the saved labels; arbitrary map values are private.
                return {key: label_fields(value) if isinstance(value, dict) else {}
                        for key, value in raw.items() if key.strip()}
            return []

        if isinstance(data.get("speakers"), (list, dict)):
            filtered["speakers"] = clean_speakers(data["speakers"])

        raw_diar = data.get("diarization")
        if isinstance(raw_diar, dict):
            clean_diar = {}
            if isinstance(raw_diar.get("speakers"), (list, dict)):
                clean_diar["speakers"] = clean_speakers(raw_diar["speakers"])
'''+s[end:]
p.write_text(s,encoding='utf8',newline='\n')
(out/'astra-server-repair.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='worker/server.py',tofile='reviewed/server.py')),encoding='utf8')
p=w/'assets/dashboard/index.html';old=p.read_text(encoding='utf8');s=old
s=change(s,'      selectedYoink: null,','      selectedYoink: null,\n      selectedYoinkRequest: 0,')
s=change(s,'        rawSpeakers.forEach((speaker, index) => {','        rawSpeakers.forEach((speaker) => {')
s=change(s,'            : firstValue(speaker.name, speaker.label, speaker.id, `Speaker ${index + 1}`);','            : speaker && firstValue(speaker.name, speaker.label, speaker.id);')
s=change(s,'return raw.split(/\\n+/).filter(Boolean).slice(0, 12).map((text, index) => ({ start: index * 30, text }));','return raw.split(/\\n+/).filter(Boolean).slice(0, 12).map((text) => ({ text }));')
s=change(s,'      return Array.isArray(raw) ? raw.filter(Boolean) : [];','''      return Array.isArray(raw)
        ? raw.filter((segment) => typeof segment === "string" || (segment && typeof segment === "object" && !Array.isArray(segment)))
          .map((segment) => typeof segment === "string" ? { text: segment } : segment)
        : [];''')
start=s.index('    function diarizationSegments(sidecar = {}) {');end=s.index('    function shouldShowDiarization',start)
s=s[:start]+'''    function storedTime(...values) {
      for (const value of values) {
        if (typeof value !== "number" && typeof value !== "string") continue;
        if (typeof value === "string" && !value.trim()) continue;
        const seconds = Number(value);
        if (Number.isFinite(seconds) && seconds >= 0) return seconds;
      }
      return null;
    }

    function diarizationSegments(sidecar = {}) {
      return transcriptSegments(sidecar)
        .map((segment) => ({
          speaker: firstValue(segment.speaker, segment.speaker_label, segment.speaker_id),
          start: storedTime(segment.start, segment.start_seconds),
          end: storedTime(segment.end, segment.end_seconds),
        }))
        .filter((segment) => segment.speaker && segment.start !== null && segment.end !== null && segment.end > segment.start);
    }

'''+s[end:]
s=change(s,'            const label = [fmtTimestamp(segment.start), speaker].filter(Boolean).join(" | ");','''            const start = storedTime(segment.start, segment.start_seconds);
            const label = [start === null ? "time not stored" : fmtTimestamp(start), speaker].filter(Boolean).join(" | ");''')
s=change(s,'    async function openYoinkDetail(row) {\n      state.selectedYoink', '    async function openYoinkDetail(row) {\n      const request = ++state.selectedYoinkRequest;\n      state.selectedYoink')
s=change(s,'if (videoIdOf(state.selectedYoink) !== videoId) return;','if (state.selectedYoinkRequest !== request) return;',4)
s=change(s,'if (videoIdOf(state.selectedYoink) === videoId) {','if (state.selectedYoinkRequest === request) {')
p.write_text(s,encoding='utf8',newline='\n')
(out/'astra-dashboard-repair.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='worker/dashboard.html',tofile='reviewed/dashboard.html')),encoding='utf8')
print('Applied six scoped source corrections; no test assertion changed.')
