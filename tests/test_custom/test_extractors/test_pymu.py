import pytest
from pathlib import Path
import fitz
from src.components.extractors.schemas.medical_extractor_configs import PyMuPdfExtractorConfig
from src.components.extractors.schemas.extract_result import ExtractResult
from src.components.extractors.pymu_extractor import PyMuPdfExtractor


def create_test_pdf(path, pages=1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Hello from page {i + 1}.")
    doc.save(str(path))
    doc.close()


class TestPyMuPdfExtractorConfig:
    def test_defaults(self):
        config = PyMuPdfExtractorConfig()
        assert config.extract_images is True
        assert config.output_image_dir == "storage/images"

    def test_custom(self):
        config = PyMuPdfExtractorConfig(extract_images=False, output_image_dir="/tmp/img")
        assert config.extract_images is False
        assert config.output_image_dir == "/tmp/img"


class TestPyMuPdfExtractor:
    def test_extract_single_page_pdf(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        create_test_pdf(pdf_path, pages=1)
        config = {"extract_images": False}
        result = PyMuPdfExtractor(config).extract(str(pdf_path))
        assert isinstance(result, ExtractResult)
        assert "Hello from page 1" in result.markdown
        assert result.images == []

    def test_extract_multi_page_pdf(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        create_test_pdf(pdf_path, pages=3)
        config = {"extract_images": False}
        result = PyMuPdfExtractor(config).extract(str(pdf_path))
        assert "Hello from page 1" in result.markdown
        assert "Hello from page 3" in result.markdown

    def test_extract_with_images_enabled(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Text with image.")
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), False)
        pix.clear_with()
        page.insert_image(fitz.Rect(100, 100, 104, 104), pixmap=pix)
        doc.save(str(pdf_path))
        doc.close()
        output_dir = tmp_path / "images"
        config = {"extract_images": True, "output_image_dir": str(output_dir)}
        result = PyMuPdfExtractor(config).extract(str(pdf_path))
        assert "Text with image" in result.markdown
        assert len(result.images) > 0

    def test_extract_result_dataclass(self):
        result = ExtractResult(markdown="some text", images=["img1.png"])
        assert result.markdown == "some text"
        assert result.images == ["img1.png"]
