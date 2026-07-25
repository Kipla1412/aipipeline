"""DICOM medical imaging extractor.

Extracts metadata and generates preview images from DICOM (.dcm) files.

Design goals:
  - Generic — supports CT, MRI, PET, US, XA, MG, SC etc. without modality-specific code
  - Open/Closed — new tags/mappings added via configuration, not logic changes
  - Type-safe — preserve native Python types (MultiValue→list, IS→float, DS→float, etc.)
  - Multi-frame aware — auto-selects middle slice for volumetric datasets
  - Rescale-aware — applies RescaleSlope/Intercept to convert to Hounsfield Units (CT) or
    physical units before window/level normalization

Public API unchanged — returns ExtractResult exactly as before.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .base import BaseExtractor
from .schemas.medical_extractor_configs import DicomExtractorConfig
from .schemas.extract_result import ExtractResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tag → metadata key mapping (tag_group, tag_element) → key_name
# ---------------------------------------------------------------------------

DICOM_TAG_MAP: dict[tuple[int, int], str] = {
    # Patient
    (0x0010, 0x0010): "patient_name",
    (0x0010, 0x0020): "patient_id",
    (0x0010, 0x1010): "patient_age",
    (0x0010, 0x0040): "patient_sex",
    # Study
    (0x0020, 0x000D): "study_uid",
    (0x0008, 0x0020): "study_date",
    (0x0008, 0x1030): "study_description",
    (0x0008, 0x0060): "modality",
    (0x0008, 0x0008): "image_type",
    (0x0008, 0x0080): "institution_name",
    # Series
    (0x0020, 0x000E): "series_uid",
    (0x0008, 0x103E): "series_description",
    (0x0018, 0x0015): "body_part_examined",
    (0x0018, 0x1030): "protocol_name",
    (0x0018, 0x5100): "patient_position",
    # Instance
    (0x0008, 0x0018): "sop_instance_uid",
    # Equipment
    (0x0008, 0x0070): "manufacturer",
    (0x0008, 0x1090): "manufacturer_model_name",
    # Acquisition geometry
    (0x0028, 0x0010): "rows",
    (0x0028, 0x0011): "columns",
    (0x0028, 0x0030): "pixel_spacing",
    (0x0018, 0x0050): "slice_thickness",
    (0x0018, 0x0088): "spacing_between_slices",
    # Window / Level
    (0x0028, 0x1050): "window_center",
    (0x0028, 0x1051): "window_width",
    # Contrast
    (0x0018, 0x0010): "contrast_agent",
    # Rescale
    (0x0028, 0x1052): "rescale_intercept",
    (0x0028, 0x1053): "rescale_slope",
}


def _normalize_dicom_value(value: Any) -> Any:
    """Convert a raw pydicom element value into a JSON-friendly Python type.

    Rules (order matters):
      - None / empty → None
      - pydicom MultiValue  → list of strings
      - pydicom PersonName   → str
      - pydicom UID          → str
      - bytes                → decoded str (ascii, replace)
      - numpy array          → list (flat) or int if scalar
      - pydicom DataElement  → recurse into .value
      - lists/tuples         → copy with each element normalized
      - IS / DS strings      → int / float if possible, else str
      - enum                 → str
      - anything else        → passed through unchanged
    """
    if value is None:
        return None
    if hasattr(value, "original_string"):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace").strip() or None
    if hasattr(value, "value") and not isinstance(value, (int, float, str, list, tuple, dict)):
        return _normalize_dicom_value(value.value)

    # pydicom MultiValue
    if isinstance(value, (list, tuple)) and not isinstance(value, str):
        return [_normalize_dicom_value(v) for v in value]

    # numpy scalars / arrays
    if hasattr(value, "item"):
        v = value.item()
        if isinstance(v, (bytes,)):
            return v.decode("ascii", errors="replace").strip()
        return v if not isinstance(v, float) or v != v else v  # NaN→float

    if isinstance(value, str):
        # IS (Integer String) or DS (Decimal String) → numeric if parseable
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            return int(stripped)
        try:
            return float(stripped)
        except (ValueError, OverflowError):
            pass
        return stripped

    return value


# ---------------------------------------------------------------------------
# DicomExtractor
# ---------------------------------------------------------------------------

class DicomExtractor(BaseExtractor):
    """Extracts metadata + preview images from DICOM files.

    Modality-agnostic — works for CT, MRI, PET, US, XA, MG, SC etc.
    Adding new tags only requires extending DICOM_TAG_MAP.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = DicomExtractorConfig(**config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, file_path: str) -> ExtractResult:
        path = Path(file_path)
        logger.info(f"Reading DICOM: {path.name}")

        ds = self._read_dataset(path)

        metadata = self._extract_metadata(ds)
        images = self._generate_preview(ds, path, metadata) if self.config.extract_preview else []
        markdown = self._build_markdown(path.name, metadata)

        logger.info(f"DICOM extraction complete — {len(markdown)} chars, {len(images)} preview(s)")
        return ExtractResult(markdown=markdown, images=images, dicom_metadata=metadata, source_type="dicom")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_dataset(path: Path):
        try:
            import pydicom
        except ImportError:
            raise ImportError("pydicom is required for DICOM. Install: pip install pydicom")
        return pydicom.dcmread(str(path), force=True)

    @staticmethod
    def _extract_metadata(ds) -> dict[str, Any]:
        """Walk DICOM_TAG_MAP, strip each value via _normalize_dicom_value."""
        metadata: dict[str, Any] = {}
        for (group, elem), key in DICOM_TAG_MAP.items():
            tag_key = (group, elem)
            if tag_key in ds:
                metadata[key] = _normalize_dicom_value(ds[tag_key].value)

        # Hard-coded fallbacks for common attributes not in tag map
        for attr in ("Rows", "Columns", "NumberOfFrames"):
            if hasattr(ds, attr) and getattr(ds, attr) is not None:
                metadata[attr.lower()] = int(getattr(ds, attr))

        return metadata

    def _generate_preview(self, ds, path: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate a window-leveled PNG preview from the pixel array.

        Pipeline:  pixel_array → RescaleSlope/Intercept → HU → Window/Level → PNG

        For multi-frame (3D) volumes, the middle slice is selected.
        """
        if not hasattr(ds, "pixel_array"):
            logger.debug("No pixel_array — skipping preview")
            return []

        try:
            pixel_array = ds.pixel_array

            # --- Multi-frame handling: pick middle slice ---
            slice_index = 0
            if pixel_array.ndim == 3:
                slice_index = pixel_array.shape[0] // 2
                pixel_array = pixel_array[slice_index]
                logger.debug(f"Multi-frame volume — using slice {slice_index}/{getattr(ds, 'NumberOfFrames', 'unknown')}")

            # --- Rescale to Hounsfield Units (or physical units) ---
            slope = metadata.get("rescale_slope", 1.0)
            intercept = metadata.get("rescale_intercept", 0.0)
            hu_array = pixel_array.astype(np.float64) * float(slope) + float(intercept)

            # --- Window / Level ---
            wc = metadata.get("window_center")
            ww = metadata.get("window_width")

            if wc is not None and ww is not None:
                low = float(wc) - float(ww) / 2
                high = float(wc) + float(ww) / 2
                hu_array = np.clip(hu_array, low, high)
            else:
                low = float(hu_array.min())
                high = float(hu_array.max())

            # Normalize to 0-255
            if high > low:
                img_data = ((hu_array - low) / (high - low) * 255).clip(0, 255).astype(np.uint8)
            else:
                img_data = np.zeros_like(hu_array, dtype=np.uint8)

            # --- Save PNG ---
            preview_filename = f"{path.stem}_preview.png"
            preview_path = Path(self.config.output_image_dir) / preview_filename
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(img_data).save(str(preview_path))

            logger.info(f"Preview saved: {preview_path} (slice={slice_index}, {img_data.shape})")

            return [{"path": str(preview_path), "type": "preview", "slice_index": slice_index}]

        except Exception as exc:
            logger.warning(f"Preview generation failed for {path.name}: {exc}")
            return []

    @staticmethod
    def _build_markdown(filename: str, metadata: dict[str, Any]) -> str:
        """Produce an LLM-friendly markdown summary.

        Includes clinically relevant fields only.  UIDs live in dicom_metadata,
        not in the markdown — they add noise for LLM consumption.
        """

        def _s(key: str, fallback: str = "N/A") -> str:
            v = metadata.get(key)
            return str(v) if v is not None else fallback

        rows = _s("rows")
        columns = _s("columns")
        modality = _s("modality")
        study_desc = _s("study_description") or _s("series_description")
        institution = _s("institution_name")
        manufacturer = _s("manufacturer")
        model = _s("manufacturer_model_name") or _s("model_name")

        # Assemble
        lines = [f"# {modality} Study: {filename}", ""]
        lines.append(f"- **Patient:** {_s('patient_name')}")
        lines.append(f"- **Modality:** {modality}")
        if study_desc != "N/A":
            lines.append(f"- **Description:** {study_desc}")
        lines.append(f"- **Date:** {_s('study_date')}")
        if institution != "N/A":
            lines.append(f"- **Institution:** {institution}")
        lines.append(f"- **Equipment:** {manufacturer} {model}" if manufacturer != "N/A" else "")
        lines.append("")
        lines.append(f"- **Rows × Columns:** {rows} × {columns}")
        lines.append(f"- **Pixel Spacing:** {_s('pixel_spacing')}")
        lines.append(f"- **Slice Thickness:** {_s('slice_thickness')}")

        # Remove trailing blank lines
        return "\n".join(l for l in lines if l.strip() != "" or l == "") + "\n"
