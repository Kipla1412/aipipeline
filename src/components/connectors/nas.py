import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base import BaseConnector
from .schemas.nasconfig import NASConfig

logger = logging.getLogger(__name__)


class NASFileSystemSession:
    def __init__(self, config: NASConfig):
        self.config = config

    def get_new_files(self) -> List[Path]:
        target_dir = Path(self.config.nas_dir_path)
        found_files = []
        for file_path in target_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.config.allowed_extensions:
                found_files.append(file_path)
        logger.info(f"NAS scan completed. Discovered {len(found_files)} files.")
        return found_files


class NASConnector(BaseConnector):
    def __init__(self, config: Dict[str, Any]):
        self.config = NASConfig(**config)
        self._session: Optional[NASFileSystemSession] = None

    async def __call__(self):
        return await self.connect()

    async def connect(self):
        if self._session is None:
            self._session = NASFileSystemSession(config=self.config)
        return self._session

    async def verify_file_stability(self, file_path: Path) -> bool:
        historical_size = -1
        retries = self.config.stability_retries
        delay = self.config.stability_delay_seconds
        for _ in range(retries):
            if not file_path.exists():
                return False
            current_size = file_path.stat().st_size
            if current_size == historical_size and current_size > 0:
                return True
            historical_size = current_size
            await asyncio.sleep(delay)
        return True

    async def close(self):
        if self._session:
            self._session = None
