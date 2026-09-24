import sys
from pathlib import Path

# The Astra-authored checks import one another as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
