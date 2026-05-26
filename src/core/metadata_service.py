import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from src.infrastructure.mutagen_wrapper import MutagenWrapper
from src.utils.constants import SUPPORTED_AUDIO_FORMATS
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MetadataService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cache = {}
        self._cache_lock = threading.RLock()
        self._max_cache_size = 1000
        self._initialized = True

    def read_metadata(self, file_path: str) -> Dict[str, any]:
        with self._cache_lock:
            if file_path in self._cache:
                return self._cache[file_path].copy()

        metadata = MutagenWrapper.read_metadata(file_path)
        metadata["path"] = file_path

        with self._cache_lock:
            self._cache[file_path] = metadata.copy()
            self._trim_cache()

        return metadata

    def scan_directory(
        self,
        directory: str,
        progress_callback: Optional[Callable] = None,
        max_workers: int = 4,
        recursive: bool = False
    ) -> List[Dict[str, any]]:
        if recursive:
            logger.warning("Recursive scan is disabled for performance reasons")
            recursive = False

        logger.info(f"Scanning directory: {directory}, recursive={recursive}")

        if not os.path.exists(directory):
            logger.warning(f"Directory does not exist: {directory}")
            return []
        if not os.path.isdir(directory):
            logger.warning(f"Path is not a directory: {directory}")
            return []

        audio_files = []
        if recursive:
            for root, _, files in os.walk(directory):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_AUDIO_FORMATS:
                        audio_files.append(os.path.join(root, file))
        else:
            # Only scan current directory, not subdirectories
            try:
                entries = os.listdir(directory)
                logger.info(f"Directory {directory} contains {len(entries)} entries")
                for file in sorted(entries):
                    full_path = os.path.join(directory, file)
                    if os.path.isfile(full_path):
                        ext = os.path.splitext(file)[1].lower()
                        if ext in SUPPORTED_AUDIO_FORMATS:
                            audio_files.append(full_path)
                            logger.debug(f"Found audio file: {full_path}")
            except PermissionError:
                logger.warning(f"Permission denied: {directory}")
                return []
            except OSError as e:
                logger.warning(f"OS error reading directory {directory}: {e}")
                return []

        logger.info(f"Found {len(audio_files)} audio files to process in {directory}")

        results = []
        total = len(audio_files)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self.read_metadata, file_path): file_path
                for file_path in audio_files
            }

            completed = 0
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    metadata = future.result()
                    results.append(metadata)
                except Exception as e:
                    logger.error(f"Error scanning {file_path}: {e}")

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        logger.info(f"Scanned {total} files, found {len(results)} valid audio files in {directory}")
        return results

    def _trim_cache(self) -> None:
        if len(self._cache) > self._max_cache_size:
            items_to_remove = list(self._cache.keys())[:len(self._cache) - self._max_cache_size]
            for key in items_to_remove:
                del self._cache[key]
