import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.components.extractors.dicom import DicomExtractor


def test_generate_preview_handles_missing_pixels(tmp_path) -> None:
    extractor = DicomExtractor({"output_image_dir": str(tmp_path), "extract_preview": True})

    class DummyDS:
        pixel_array = None

    result = extractor._generate_preview(DummyDS(), Path("dummy.dcm"), {})

    assert result == []
