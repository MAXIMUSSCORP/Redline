import io
import tokenize
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "src" / "redline" / "rules"
ALLOWED = {0, 1, 2, 3, 100}


def _numbers(path: Path):
    for tok in tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline):
        if tok.type == tokenize.NUMBER:
            yield tok.start[0], tok.string


def test_rules_hold_no_numeric_literal_beyond_allowed():
    bad = []
    for path in sorted(RULES_DIR.glob("*.py")):
        for line, text in _numbers(path):
            if float(text.replace("_", "")) not in ALLOWED:
                bad.append(f"{path.name}:{line} {text}")
    assert not bad, bad
