from pydantic import BaseModel, Field


class PyMuPdfExtractorConfig(BaseModel):
    extract_images: bool = Field(default=True, description="Enable extracting embedded images from PDF")
    output_image_dir: str = Field(default="storage/images", description="Directory to save extracted images")


class ImageAnalyzerConfig(BaseModel):
    api_key: str = Field(..., description="OpenAI API key")
    model_name: str = Field(default="gpt-4o", description="Vision model for image description")
