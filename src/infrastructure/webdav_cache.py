import time
import threading
from typing import Dict, List, Optional, Tuple

from src.infrastructure.webdav_client import FileInfo
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR_CACHE: Dict[str, Tuple[float, List[FileInfo]]] = {}
_URL_CACHE: Dict[str, Tuple[float, str, bool]] = {}
_LOCK = threading.Lock()


def get(account_id: str, path: str, ttl: int = 600) -> Optional[List[FileInfo]]:
    key = _dir_key(account_id, path)
    with _LOCK:
        entry = _DIR_CACHE.get(key)
        if entry is None:
            return None
        ts, items = entry
        if time.time() - ts > ttl:
            del _DIR_CACHE[key]
            return None
        return items


def put(account_id: str, path: str, items: List[FileInfo]) -> None:
    key = _dir_key(account_id, path)
    with _LOCK:
        _DIR_CACHE[key] = (time.time(), items)


def get_download_url(account_id: str, path: str, ttl: int = 300) -> Optional[Tuple[str, bool]]:
    key = _url_key(account_id, path)
    with _LOCK:
        entry = _URL_CACHE.get(key)
        if entry is None:
            return None
        ts, url, is_direct = entry
        if time.time() - ts > ttl:
            del _URL_CACHE[key]
            return None
        return url, is_direct


def put_download_url(account_id: str, path: str, url: str, is_direct: bool) -> None:
    key = _url_key(account_id, path)
    with _LOCK:
        _URL_CACHE[key] = (time.time(), url, is_direct)


def invalidate(account_id: str, path: str = "") -> None:
    with _LOCK:
        if path:
            dkey = _dir_key(account_id, path)
            _DIR_CACHE.pop(dkey, None)
            ukey = _url_key(account_id, path)
            _URL_CACHE.pop(ukey, None)
        else:
            prefix = f"{account_id}:"
            to_del = [k for k in _DIR_CACHE if k.startswith(prefix)]
            for k in to_del:
                del _DIR_CACHE[k]
            to_del = [k for k in _URL_CACHE if k.startswith(prefix)]
            for k in to_del:
                del _URL_CACHE[k]


def _dir_key(account_id: str, path: str) -> str:
    return f"d:{account_id}:{path.rstrip('/')}"


def _url_key(account_id: str, path: str) -> str:
    return f"u:{account_id}:{path.rstrip('/')}"
