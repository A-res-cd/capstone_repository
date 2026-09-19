import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.pdf_extractor import extract_capstone_data

data = extract_capstone_data(str(ROOT / "instance/uploads/manuscripts/EvalOn_Manuscript.pdf"))
print(f"Extracted capstone data: {data}")
