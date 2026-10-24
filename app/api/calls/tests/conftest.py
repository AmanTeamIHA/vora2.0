import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_API_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "contracts" / "src"))
