from pathlib import Path
root = Path(__file__).resolve().parents[1]
text = (root / '_scratch/launch_vad_cycle01.py').read_text()
for old, new in {
    'One reviewed cycle-refusal diagnostic': 'One reviewed partial selected-root diagnostic',
    'vad-symbolic-cycle-diagnostic-proposal01': 'vad-selected-root-projection-proposal01',
    '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd': '0b62dcac9962ee0620ed8c8af6deca169ce5aeab215994b637f5902dd79ddb73',
    'CYCLE-DIAGNOSTIC-FINAL-REVIEW.md': 'SELECTED-PROJECTION-FINAL-REVIEW.md',
    '918405d3bb987bfbc9112cc7e2a43b7fbd8ccec6b4fa576d25a42e1632e26b04': '1adcf5ed8fc1d5ae67d60b18a09d70f0494d28f7912afc9440804f1ad53b7638',
    'vad-symbolic-cycle01-launch': 'vad-symbolic-projection01-launch',
    'VAD-CYCLE-RUN01-BRIEF-2026-09-13.md': 'VAD-PROJECTION-RUN01-BRIEF-2026-09-13.md',
    'symbolic-cycle01': 'symbolic-projection01',
    'One fixed-hash static cycle-refusal diagnostic': 'One fixed-hash partial selected-root static diagnostic retaining whole-graph refusal',
}.items():
    assert old in text, old
    text = text.replace(old, new)
with (root / '_scratch/launch_vad_projection01.py').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
