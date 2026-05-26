from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from src.infrastructure.subtitle_parser import SubtitleLine


class TranscriptionInterface(ABC):
    meta: Dict[str, Any] = {
        "id": "",
        "name": "",
        "version": "",
        "author": "",
        "description": "",
    }

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @property
    def plugin_id(self) -> str:
        return self.meta.get("id", "")

    @property
    def name(self) -> str:
        return self.meta.get("name", "")

    @property
    def version(self) -> str:
        return self.meta.get("version", "")

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_models(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def install(self, progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        pass

    @abstractmethod
    def uninstall(self) -> bool:
        pass

    @abstractmethod
    def download_model(self, model_name: str, progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        model_name: str = "base",
        language: str = None,
        device: str = "auto",
        compute_type: str = "auto",
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Optional[List[SubtitleLine]]:
        pass
