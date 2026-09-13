"""Adapt the reviewed root synthetic launcher to the new reporting-only protocol."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
text = (root / '_scratch/qualify_symbolic_adapter_astra01.py').read_text()
replacements = {
    'Independent run of the exact reviewed adapter synthetic protocol.': 'Independent run of the reviewed reporting-only cycle diagnostic protocol.',
    'vad-symbolic-adapter-proposal01': 'vad-symbolic-cycle-diagnostic-proposal01',
    'astra-symbolic-adapter01': 'astra-cycle-diagnostic01',
    'qualify_adapter.py': 'qualify_cycle.py',
    'astra-adapter01': 'astra-cycle01',
    'Same 24 synthetic cases': 'Same 36 synthetic cases',
    '0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc': '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd',
    'f665893556812d2f12915f51397895a59359588304363c691fe569748e1587a9': 'f76fa88e58bba46130c2b8d44c7d17543ff46334c73976adb138efa0fa169f6a',
}
for old, new in replacements.items():
    assert old in text, old
    text = text.replace(old, new)
anchor = "expected = {\n"
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + "    'before/read_symbolic_inventory.py': '0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc',\n")
target = root / '_scratch/qualify_cycle_astra01.py'
assert not target.exists()
target.write_text(text, encoding='utf8', newline='\n')
