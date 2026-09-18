from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_sample_data_exists():
    assert (ROOT / "data" / "sample.csv").is_file()


def test_readme_long_enough():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert len(text) >= 200


def test_summary_not_empty():
    rows = main.load_rows(ROOT / "data" / "sample.csv")
    conn = main.build_db(rows)
    text = main.summarize(conn)
    assert "total=" in text
    assert float(text.split("total=")[1].splitlines()[0]) > 0


def test_main_ok():
    assert main.main([]) == 0
