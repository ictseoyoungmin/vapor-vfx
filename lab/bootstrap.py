"""Research may consume shared validation utilities; runtime never imports Lab."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
