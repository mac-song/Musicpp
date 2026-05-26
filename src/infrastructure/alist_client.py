import json
import os
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class AListClient:
    @staticmethod
    def is_alist_server(server_url: str, timeout: int = 5) -> bool:
        server_url = server_url.rstrip("/")
        try:
            url = server_url + "/api/public/settings"
            req = Request(url, method="GET")
            with urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("code") == 200
        except Exception:
            pass
        return False

    @staticmethod
    def login(server_url: str, username: str, password: str, timeout: int = 15) -> Optional[str]:
        server_url = server_url.rstrip("/")
        url = server_url + "/api/auth/login"
        body = json.dumps({
            "username": username,
            "password": password,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        req = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 200:
                    return data.get("data", {}).get("token", "")
                logger.warning(f"AList login failed: {data.get('message', '')}")
                return None
        except Exception as e:
            logger.warning(f"AList login error: {e}")
            return None

    @staticmethod
    def list_dir(
        server_url: str,
        path: str,
        token: str = "",
        password: str = "",
        page: int = 1,
        per_page: int = 100,
        timeout: int = 30,
    ) -> Tuple[List[Dict], bool]:
        server_url = server_url.rstrip("/")
        url = server_url + "/api/fs/list"
        payload = {
            "path": path,
            "password": password,
            "page": page,
            "per_page": per_page,
        }
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = token

        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 200:
                    content = data.get("data", {}).get("content", []) or []
                    total = data.get("data", {}).get("total", 0)
                    has_more = page * per_page < total
                    return content, has_more
                logger.warning(f"AList list_dir failed: {data.get('message', '')}")
                return [], False
        except Exception as e:
            logger.warning(f"AList list_dir error: {e}")
            return [], False

    @staticmethod
    def get_file_info(
        server_url: str,
        path: str,
        token: str = "",
        password: str = "",
        timeout: int = 30,
    ) -> Optional[Dict]:
        server_url = server_url.rstrip("/")
        url = server_url + "/api/fs/get"
        payload = {
            "path": path,
            "password": password,
        }
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = token

        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 200:
                    return data.get("data", {})
                logger.warning(f"AList get_file_info failed: {data.get('message', '')}")
                return None
        except Exception as e:
            logger.warning(f"AList get_file_info error: {e}")
            return None

    @staticmethod
    def get_download_url(
        server_url: str,
        path: str,
        token: str = "",
        password: str = "",
        timeout: int = 30,
    ) -> Optional[str]:
        info = AListClient.get_file_info(server_url, path, token, password, timeout)
        if info:
            raw_url = info.get("raw_url", "")
            if raw_url:
                return raw_url
            sign = info.get("sign", "")
            base = server_url
            encoded_path = quote(path, safe="/")
            if sign:
                return f"{base}/d{encoded_path}?sign={sign}"
            return f"{base}/d{encoded_path}"
        return None

    @staticmethod
    def search(
        server_url: str,
        parent_path: str,
        keyword: str,
        token: str = "",
        password: str = "",
        page: int = 1,
        per_page: int = 100,
        timeout: int = 30,
    ) -> Tuple[List[Dict], bool]:
        server_url = server_url.rstrip("/")
        url = server_url + "/api/fs/search"
        payload = {
            "parent": parent_path,
            "keywords": keyword,
            "password": password,
            "page": page,
            "per_page": per_page,
        }
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = token

        body = json.dumps(payload).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 200:
                    content = data.get("data", {}).get("content", []) or []
                    total = data.get("data", {}).get("total", 0)
                    has_more = page * per_page < total
                    return content, has_more
                return [], False
        except Exception as e:
            logger.warning(f"AList search error: {e}")
            return [], False

    @staticmethod
    def convert_to_file_infos(
        alist_items: List[Dict],
        parent_path: str,
    ) -> List:
        from src.infrastructure.webdav_client import FileInfo
        from src.utils.constants import SUPPORTED_AUDIO_FORMATS, PLAYLIST_FORMATS

        results = []
        for item in alist_items:
            name = item.get("name", "")
            is_dir = item.get("is_dir", False)
            size = item.get("size", 0)
            modified = item.get("modified", "")
            item_path = parent_path.rstrip("/") + "/" + name

            fi = FileInfo(
                name=name,
                path=item_path,
                is_dir=is_dir,
                size=size,
                modified=modified,
                content_type="",
            )
            results.append(fi)
        return results
