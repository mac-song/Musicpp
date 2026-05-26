import hashlib
import json
import os
import threading
import time
from typing import Any, Dict, Optional
from urllib.request import ProxyHandler, build_opener, install_opener

import requests

from src.utils.constants import CACHE_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def get_proxy_settings():
    from src.business.config_manager import ConfigManager
    cfg = ConfigManager()
    proxy_type = cfg.get("Network", "ProxyType", 0)
    if proxy_type == 0:
        return None
    addr = cfg.get("Network", "ProxyAddr", "127.0.0.1")
    port = cfg.get("Network", "ProxyPort", 7890)
    scheme = "socks5" if proxy_type == 2 else "http"
    proxy_url = f"{scheme}://{addr}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def get_proxy_url():
    proxies = get_proxy_settings()
    if not proxies:
        return None
    return proxies.get("http") or proxies.get("https")


def apply_urllib_proxy():
    proxies = get_proxy_settings()
    if proxies:
        proxy_handler = ProxyHandler(proxies)
        opener = build_opener(proxy_handler)
        install_opener(opener)
        logger.info(f"urllib proxy installed: {proxies}")
    else:
        proxy_handler = ProxyHandler({})
        opener = build_opener(proxy_handler)
        install_opener(opener)


class NetworkService:
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
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
        })
        self._cache_dir = os.path.join(CACHE_DIR, "network")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._cache_ttl = 86400
        self._max_cache_files = 200
        self._max_cache_bytes = 50 * 1024 * 1024
        self._initialized = True
        self.apply_proxy()

    def apply_proxy(self):
        proxies = get_proxy_settings()
        if proxies:
            proxy_url = proxies.get("http") or proxies.get("https") or ""
            if proxy_url.startswith("socks5"):
                try:
                    import socksio
                except ImportError:
                    try:
                        import PySocks
                    except ImportError:
                        logger.warning("SOCKS5 proxy requires 'pysocks' package. Install with: pip install pysocks")
                        self._session.proxies.clear()
                        return
            self._session.proxies.update(proxies)
            logger.info(f"requests proxy applied: {proxies}")
        else:
            self._session.proxies.clear()

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 10,
        retries: int = 3,
        use_cache: bool = False,
        cache_ttl: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        if use_cache:
            cache_key = self._generate_cache_key(method, url, params, data, json_data)
            cached = self._get_cache(cache_key, cache_ttl or self._cache_ttl)
            if cached is not None:
                return cached

        request_headers = dict(self._session.headers)
        if headers:
            request_headers.update(headers)

        for attempt in range(retries):
            try:
                response = self._session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=data,
                    headers=request_headers,
                    json=json_data,
                    timeout=timeout
                )
                response.raise_for_status()

                try:
                    result = response.json()
                except ValueError:
                    result = {"text": response.text}

                if use_cache:
                    self._set_cache(cache_key, result)

                return result

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    import random
                    time.sleep(min(2 ** attempt + random.random(), 10))
                else:
                    logger.error(f"Request failed after {retries} attempts: {url}")
                    return None

        return None

    def get(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: int = 10,
        use_cache: bool = False
    ) -> Optional[Dict[str, Any]]:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout, use_cache=use_cache)

    def _generate_cache_key(self, method: str, url: str, params: Optional[Dict], data: Optional[Dict], json_data: Optional[Dict]) -> str:
        key_data = f"{method}:{url}:{json.dumps(params, sort_keys=True)}:{json.dumps(data, sort_keys=True)}:{json.dumps(json_data, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_cache(self, cache_key: str, ttl: int) -> Optional[Dict]:
        cache_path = os.path.join(self._cache_dir, f"{cache_key}.json")
        if not os.path.exists(cache_path):
            return None

        if time.time() - os.path.getmtime(cache_path) > ttl:
            os.remove(cache_path)
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _set_cache(self, cache_key: str, data: Dict) -> None:
        cache_path = os.path.join(self._cache_dir, f"{cache_key}.json")
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self._evict_cache()
        except Exception as e:
            logger.warning(f"Failed to write cache: {e}")

    def _evict_cache(self) -> None:
        try:
            files = []
            total_size = 0
            for f in os.listdir(self._cache_dir):
                if not f.endswith(".json"):
                    continue
                path = os.path.join(self._cache_dir, f)
                try:
                    size = os.path.getsize(path)
                    mtime = os.path.getmtime(path)
                    total_size += size
                    files.append((path, size, mtime))
                except OSError:
                    continue

            if len(files) <= self._max_cache_files and total_size <= self._max_cache_bytes:
                return

            files.sort(key=lambda x: x[2])

            while files and (len(files) > self._max_cache_files or total_size > self._max_cache_bytes):
                path, size, _ = files.pop(0)
                try:
                    os.remove(path)
                    total_size -= size
                except OSError:
                    continue
        except Exception as e:
            logger.warning(f"Cache eviction error: {e}")
