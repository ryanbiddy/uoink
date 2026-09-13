"""Adapt the reviewed root launcher to the exact 63-case projection protocol."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
text = (root / '_scratch/qualify_cycle_astra01.py').read_text()
replacements = {
    'reporting-only cycle diagnostic': 'partial selected-root projection',
    'vad-symbolic-cycle-diagnostic-proposal01': 'vad-selected-root-projection-proposal01',
    'astra-cycle-diagnostic01': 'astra-selected-projection01',
    'qualify_cycle.py': 'qualify_projection.py',
    'astra-cycle01': 'astra-projection01',
    'Same 36 synthetic cases': 'Same 63 synthetic cases',
    '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd': '0b62dcac9962ee0620ed8c8af6deca169ce5aeab215994b637f5902dd79ddb73',
    '0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc': '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd',
    'f76fa88e58bba46130c2b8d44c7d17543ff46334c73976adb138efa0fa169f6a': '6e0a19710f0a899f3d68dbff9d5d741118879d7c94fa0f42114b37208109e01a',
}
for old, new in replacements.items():
    assert old in text, old
    text = text.replace(old, new)
target = root / '_scratch/qualify_projection_astra01.py'
with target.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(text)
