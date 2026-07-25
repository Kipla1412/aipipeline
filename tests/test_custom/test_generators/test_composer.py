import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.components.generators.composer import ReportComposer


def test_compose_timeline_handles_missing_dates() -> None:
    composer = ReportComposer()
    reports = [
        {"date": None, "label": "Second", "slug": "second"},
        {"date": "2024-01-02", "label": "First", "slug": "first"},
        {"date": "", "label": "Third", "slug": "third"},
    ]

    output = composer.compose_timeline("Patient", reports)

    assert "## Unknown" in output
    assert "## 2024" in output
    assert "[[first|First]]" in output
