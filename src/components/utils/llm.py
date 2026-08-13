"""Async OpenAI-compatible LLM client — independent, no aipipeline dependency."""

import base64
import httpx
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """Reusable async LLM client. Supports text generation + vision."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout: float = 300):
        """
        Purpose:
            Initializes the LLMClient with API key, model, and optional base URL.

        Args:
            api_key: OpenAI API key.
            model: Model name, e.g. 'gpt-4o-mini'.
            base_url: Optional custom OpenAI-compatible base URL.
            timeout: Request timeout in seconds.
        """
        self._client: AsyncOpenAI | None = None
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def _get_client(self) -> AsyncOpenAI:
        """
        Purpose:
            Lazily creates and returns the async OpenAI client.

        Returns:
            AsyncOpenAI: Initialized client instance.
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=30.0),
            )
        return self._client

    async def close(self) -> None:
        """
        Purpose:
            Closes the async OpenAI client connection.
        """
        if self._client:
            await self._client.close()
            self._client = None

    async def generate(
        self, system_prompt: str, user_query: str,
        response_format: type | None = None, json_mode: bool = False,
    ) -> str:
        """
        Purpose:
            Generates a chat completion from the LLM.

        Args:
            system_prompt: System prompt instructing the model.
            user_query: User content to process.
            response_format: Optional Pydantic model for structured output.
            json_mode: Whether to request JSON object response.

        Returns:
            str: Model response. JSON string if response_format provided, else text.
        """
        client = self._get_client()
        kwargs: dict = {
            "model": self.model, "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if response_format is not None:
            completion = await client.beta.chat.completions.parse(response_format=response_format, **kwargs)
            parsed = completion.choices[0].message.parsed
            return "" if parsed is None else parsed.model_dump_json()
        else:
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""

    async def describe_image(self, system_prompt: str, image_path: str) -> str:
        """
        Purpose:
            Analyzes a medical image using LLM vision and returns a text description.

        Args:
            system_prompt: Instruction prompt for image analysis.
            image_path: Path to the image file.

        Returns:
            str: Textual description of the image.
        """
        from pathlib import Path
        path = Path(image_path)
        ext = path.suffix.lower().lstrip(".")
        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}
        mime = mime_map.get(ext, "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        client = self._get_client()
        response = await client.chat.completions.create(
            model=self.model, temperature=0.1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "Describe this medical image."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ]},
            ],
        )
        return response.choices[0].message.content or ""
