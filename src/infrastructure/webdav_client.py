import base64
import hashlib
import os
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urlparse, quote, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.utils.constants import SUPPORTED_AUDIO_FORMATS, PLAYLIST_FORMATS
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_DAV_NS = {"d": "DAV:"}


@dataclass
class FileInfo:
    name: str
    path: str
    is_dir: bool = False
    size: int = 0
    modified: str = ""
    content_type: str = ""

    @property
    def ext(self) -> str:
        return os.path.splitext(self.name)[1].lower()

    @property
    def is_audio(self) -> bool:
        return self.ext in SUPPORTED_AUDIO_FORMATS

    @property
    def is_playlist(self) -> bool:
        return self.ext in PLAYLIST_FORMATS


class WebDAVClient:
    @staticmethod
    def _is_local_host(host: str) -> bool:
        host = (host or "").lower()
        return (
            host in ("localhost", "127.0.0.1", "::1")
            or host.startswith(("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.3"))
        )

    @staticmethod
    def _is_connection_reset(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return True
        if isinstance(exc, URLError) and isinstance(exc.reason, (ConnectionResetError, ConnectionAbortedError)):
            return True
        if isinstance(exc, OSError):
            msg = str(exc)
            if "10054" in msg or "reset" in msg.lower() or "远程主机" in msg:
                return True
        if isinstance(exc, URLError) and isinstance(exc.reason, OSError):
            msg = str(exc.reason)
            if "10054" in msg or "reset" in msg.lower() or "远程主机" in msg:
                return True
        return False

    @staticmethod
    def normalize_url(url: str) -> str:
        url = url.strip()
        if not url:
            return url
        if not url.startswith(("http://", "https://")):
            lower = url.lower()
            if lower.startswith(("localhost", "127.", "192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.3")):
                url = "http://" + url
            else:
                url = "https://" + url
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        url = url.rstrip("/")
        if parsed.scheme == "https" and WebDAVClient._is_local_host(parsed.hostname):
            url = "http://" + url[len("https://"):]
        return url

    @staticmethod
    def list_dir(
        server_url: str,
        path: str,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        verify_ssl: bool = False,
    ) -> List[FileInfo]:
        server_url = WebDAVClient.normalize_url(server_url)
        url = WebDAVClient._build_url(server_url, path)
        headers = {
            "Depth": "1",
            "Content-Type": "application/xml; charset=utf-8",
        }

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:propfind xmlns:d="DAV:">'
            "<d:prop>"
            "<d:resourcetype/>"
            "<d:getcontentlength/>"
            "<d:getlastmodified/>"
            "<d:getcontenttype/>"
            "</d:prop>"
            "</d:propfind>"
        ).encode("utf-8")

        for attempt in range(2):
            try:
                resp = WebDAVClient._request_with_auth(
                    url, "PROPFIND", username, password, headers, body, timeout, verify_ssl,
                )
                xml_data = resp.read().decode("utf-8")
                return WebDAVClient._parse_multistatus(xml_data, server_url, path)
            except HTTPError as e:
                if e.code == 405:
                    logger.warning(f"WebDAV PROPFIND not allowed: {url}")
                elif e.code == 401:
                    logger.warning(f"WebDAV auth failed: {url}")
                else:
                    logger.warning(f"WebDAV HTTP error {e.code}: {url}")
                return []
            except Exception as e:
                if attempt == 0 and WebDAVClient._is_connection_reset(e):
                    import time
                    logger.info(f"WebDAV list_dir connection reset, retrying: {url}")
                    time.sleep(0.5)
                    continue
                logger.warning(f"WebDAV list_dir error: {e}")
                return []
        return []

    @staticmethod
    def test_connection(
        server_url: str,
        username: str = "",
        password: str = "",
        timeout: int = 15,
        verify_ssl: bool = False,
    ) -> tuple:
        server_url = WebDAVClient.normalize_url(server_url)
        if not server_url or not server_url.startswith(("http://", "https://")):
            return False, "服务器地址格式无效，请输入完整的 URL（如 https://dav.example.com/dav/）"

        url = server_url.rstrip("/") + "/"
        headers = {"Depth": "0"}

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:propfind xmlns:d="DAV:">'
            "<d:prop><d:resourcetype/></d:prop>"
            "</d:propfind>"
        ).encode("utf-8")

        try:
            resp = WebDAVClient._request_with_auth(
                url, "PROPFIND", username, password, headers, body, timeout, verify_ssl,
            )
            if resp.status in (200, 207):
                return True, "连接成功"
            return False, f"HTTP {resp.status}"
        except HTTPError as e:
            if e.code == 401:
                return False, "认证失败，请检查用户名和密码"
            if e.code == 405:
                try:
                    resp2 = WebDAVClient._request_with_auth(
                        url, "OPTIONS", username, password, headers, None, timeout, verify_ssl,
                    )
                    if resp2.status in (200, 204):
                        return True, "连接成功（有限支持）"
                except Exception:
                    pass
                return False, "服务器不支持 WebDAV 协议"
            return False, f"HTTP 错误: {e.code}"
        except URLError as e:
            reason = e.reason
            if isinstance(reason, socket.gaierror):
                parsed = urlparse(url)
                host = parsed.hostname or url
                return False, f"无法解析服务器地址: {host}\n请检查地址是否正确，或该服务是否支持 WebDAV 协议"
            if isinstance(reason, socket.timeout):
                return False, "连接超时，请检查服务器地址和网络"
            if "timed out" in str(reason).lower():
                return False, "连接超时，请检查服务器地址和网络"
            reason_str = str(reason).lower()
            if "ssl" in reason_str or "certificate" in reason_str or "handshake" in reason_str:
                parsed = urlparse(url)
                if parsed.scheme == "https":
                    return False, "SSL 连接失败：服务器可能不支持 HTTPS，请尝试使用 HTTP 地址（如 http://127.0.0.1:5244/dav/）"
                return False, f"SSL 连接失败: {reason}"
            if "connectionreset" in reason_str or "远程主机" in str(reason) or "reset" in reason_str:
                parsed = urlparse(url)
                if parsed.scheme == "https" and parsed.hostname in ("localhost", "127.0.0.1"):
                    return False, "连接被重置：本地服务器通常使用 HTTP 而非 HTTPS\n请将地址改为 http://127.0.0.1:5244/dav/"
                return False, f"连接被重置: {reason}"
            if "refused" in reason_str or "拒绝" in str(reason):
                return False, "连接被拒绝：请检查服务器是否已启动，端口是否正确"
            return False, f"无法连接: {reason}"
        except Exception as e:
            e_str = str(e).lower()
            if "ssl" in e_str:
                return False, "SSL 连接失败：服务器可能不支持 HTTPS，请尝试使用 HTTP 地址"
            return False, f"连接失败: {e}"

    @staticmethod
    def get_file_url(server_url: str, path: str) -> str:
        return WebDAVClient._build_url(server_url, path)

    @staticmethod
    def get_download_url(
        server_url: str,
        path: str,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        verify_ssl: bool = False,
        max_redirects: int = 5,
    ) -> Tuple[str, bool]:
        server_url = WebDAVClient.normalize_url(server_url)
        url = WebDAVClient._build_url(server_url, path)
        auth_header = ""
        if username:
            cred = base64.b64encode(f"{username}:{password}".encode()).decode()
            auth_header = f"Basic {cred}"

        original_host = urlparse(url).hostname
        ctx = WebDAVClient._ssl_context(verify_ssl)

        current_url = url
        for _ in range(max_redirects + 1):
            headers = {}
            current_host = urlparse(current_url).hostname
            if current_host == original_host and auth_header:
                headers["Authorization"] = auth_header

            req = Request(current_url, headers=headers, method="HEAD")
            try:
                resp = urlopen(req, timeout=timeout, context=ctx)
                final_url = resp.geturl()
                if final_url != current_url:
                    current_url = final_url
                    continue
                is_direct = urlparse(current_url).hostname != original_host
                return current_url, is_direct
            except HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    location = e.headers.get("Location", "")
                    if location:
                        if not location.startswith(("http://", "https://")):
                            parsed = urlparse(current_url)
                            base = f"{parsed.scheme}://{parsed.netloc}"
                            location = base + location
                        current_url = location
                        continue
                if e.code == 200:
                    is_direct = urlparse(current_url).hostname != original_host
                    return current_url, is_direct
                logger.warning(f"WebDAV get_download_url HTTP {e.code}: {url}")
                break
            except Exception as e:
                if current_url.startswith("https://") and WebDAVClient._is_connection_reset(e):
                    parsed = urlparse(current_url)
                    if WebDAVClient._is_local_host(parsed.hostname):
                        current_url = "http://" + current_url[len("https://"):]
                        logger.info(f"WebDAV get_download_url HTTPS→HTTP fallback: {current_url}")
                        continue
                logger.warning(f"WebDAV get_download_url error: {e}")
                break

        is_direct = urlparse(current_url).hostname != original_host
        return current_url, is_direct

    @staticmethod
    def download_text(
        server_url: str,
        path: str,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        verify_ssl: bool = False,
    ) -> Optional[str]:
        server_url = WebDAVClient.normalize_url(server_url)
        url = WebDAVClient._build_url(server_url, path)

        try:
            resp = WebDAVClient._request_with_auth(
                url, "GET", username, password, {}, None, timeout, verify_ssl,
            )
            return resp.read().decode("utf-8-sig", errors="replace")
        except Exception as e:
            logger.warning(f"WebDAV download_text error: {e}")
            return None

    @staticmethod
    def build_auth_header(username: str, password: str) -> str:
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        return f"Basic {cred}"

    @staticmethod
    def _build_auth_headers(username: str, password: str, auth_type: str = "auto") -> dict:
        if not username:
            return {}
        if auth_type == "digest":
            return {}
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}

    @staticmethod
    def _build_digest_header(method: str, url: str, username: str, password: str, www_authenticate: str) -> str:
        params = {}
        for match in re.finditer(r'(\w+)=(?:"([^"]*)"|([\w/+=]+))', www_authenticate):
            key = match.group(1)
            val = match.group(2) if match.group(2) is not None else match.group(3)
            params[key] = val

        realm = params.get("realm", "")
        nonce = params.get("nonce", "")
        qop = params.get("qop", "")
        opaque = params.get("opaque", "")
        algorithm = params.get("algorithm", "MD5").upper()

        parsed = urlparse(url)
        uri = parsed.path or "/"
        if parsed.query:
            uri += "?" + parsed.query

        ha = hashlib.md5 if algorithm == "MD5" else hashlib.sha256

        ha1 = ha(f"{username}:{realm}:{password}".encode()).hexdigest()
        ha2 = ha(f"{method}:{uri}".encode()).hexdigest()

        if qop:
            cnonce = hashlib.md5(os.urandom(16)).hexdigest()[:16]
            nc = "00000001"
            response = ha(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
        else:
            cnonce = ""
            nc = ""
            response = ha(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

        header = (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", response="{response}"'
        )
        if algorithm != "MD5":
            header += f', algorithm={algorithm}'
        if qop:
            header += f', qop={qop}, nc={nc}, cnonce="{cnonce}"'
        if opaque:
            header += f', opaque="{opaque}"'

        return header

    @staticmethod
    def _request_with_auth(
        url: str,
        method: str,
        username: str = "",
        password: str = "",
        headers: dict = None,
        body: bytes = None,
        timeout: int = 30,
        verify_ssl: bool = False,
        _http_fallback: bool = True,
    ) -> object:
        ctx = WebDAVClient._ssl_context(verify_ssl)
        req_headers = dict(headers or {})
        if username:
            cred = base64.b64encode(f"{username}:{password}".encode()).decode()
            req_headers["Authorization"] = f"Basic {cred}"

        req = Request(url, data=body, headers=req_headers, method=method)
        try:
            return urlopen(req, timeout=timeout, context=ctx)
        except HTTPError as e:
            if e.code == 401 and username:
                www_auth = e.headers.get("WWW-Authenticate", "")
                if "digest" in www_auth.lower():
                    digest_header = WebDAVClient._build_digest_header(
                        method, url, username, password, www_auth
                    )
                    req_headers2 = dict(headers or {})
                    req_headers2["Authorization"] = digest_header
                    req2 = Request(url, data=body, headers=req_headers2, method=method)
                    return urlopen(req2, timeout=timeout, context=ctx)
            raise
        except Exception as e:
            if _http_fallback and url.startswith("https://") and WebDAVClient._is_connection_reset(e):
                parsed = urlparse(url)
                if WebDAVClient._is_local_host(parsed.hostname):
                    http_url = "http://" + url[len("https://"):]
                    logger.info(f"WebDAV HTTPS→HTTP fallback on connection reset: {http_url}")
                    return WebDAVClient._request_with_auth(
                        http_url, method, username, password, headers, body,
                        timeout, verify_ssl, _http_fallback=False,
                    )
            raise

    @staticmethod
    def search(
        server_url: str,
        path: str,
        keyword: str,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        verify_ssl: bool = False,
    ) -> List[FileInfo]:
        server_url = WebDAVClient.normalize_url(server_url)
        url = WebDAVClient._build_url(server_url, path)

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:searchrequest xmlns:d="DAV:">'
            "<d:basicsearch>"
            f"<d:select><d:prop><d:resourcetype/><d:getcontentlength/>"
            f"<d:getlastmodified/><d:getcontenttype/></d:prop></d:select>"
            f"<d:from><d:scope><d:href>{path}</d:href>"
            f"<d:depth>infinity</d:depth></d:scope></d:from>"
            f"<d:where><d:like><d:prop><d:displayname/></d:prop>"
            f"<d:literal>%{keyword}%</d:literal></d:like></d:where>"
            "</d:basicsearch>"
            "</d:searchrequest>"
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": "0",
        }

        try:
            resp = WebDAVClient._request_with_auth(
                url, "SEARCH", username, password, headers, body, timeout, verify_ssl,
            )
            xml_data = resp.read().decode("utf-8")
            results = WebDAVClient._parse_multistatus(xml_data, server_url, path)
            return [f for f in results if keyword.lower() in f.name.lower()]
        except HTTPError as e:
            if e.code == 405 or e.code == 501:
                logger.info("Server does not support WebDAV SEARCH")
            else:
                logger.warning(f"WebDAV SEARCH error: HTTP {e.code}")
            return []
        except Exception as e:
            logger.warning(f"WebDAV search error: {e}")
            return []

    @staticmethod
    def _build_url(server_url: str, path: str) -> str:
        base = server_url.rstrip("/")
        p = path if path.startswith("/") else f"/{path}"
        encoded_p = quote(p, safe="/")
        return f"{base}{encoded_p}"

    @staticmethod
    def _parse_multistatus(xml_data: str, server_url: str, request_path: str) -> List[FileInfo]:
        results = []
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            logger.warning(f"WebDAV XML parse error: {e}")
            return []

        request_path_norm = request_path.rstrip("/") + "/"
        if request_path_norm == "/":
            request_path_norm = "/"

        for response in root.findall("d:response", _DAV_NS):
            href_elem = response.find("d:href", _DAV_NS)
            if href_elem is None or not href_elem.text:
                continue

            href = href_elem.text
            decoded_href = unquote(href)

            base = server_url.rstrip("/")
            if decoded_href.startswith(base):
                item_path = decoded_href[len(base):]
            else:
                parsed_base = urlparse(base)
                base_path = parsed_base.path.rstrip("/")
                if base_path and decoded_href.startswith(base_path + "/"):
                    item_path = decoded_href[len(base_path):]
                elif base_path and decoded_href == base_path:
                    item_path = "/"
                else:
                    item_path = decoded_href

            item_path = item_path.rstrip("/")
            if not item_path:
                continue

            request_norm = request_path.rstrip("/")
            if item_path == request_norm:
                continue

            propstat = response.find("d:propstat", _DAV_NS)
            if propstat is None:
                continue

            prop = propstat.find("d:prop", _DAV_NS)
            if prop is None:
                continue

            is_dir = prop.find("d:resourcetype/d:collection", _DAV_NS) is not None

            size = 0
            size_elem = prop.find("d:getcontentlength", _DAV_NS)
            if size_elem is not None and size_elem.text:
                try:
                    size = int(size_elem.text)
                except ValueError:
                    pass

            modified = ""
            mod_elem = prop.find("d:getlastmodified", _DAV_NS)
            if mod_elem is not None and mod_elem.text:
                modified = mod_elem.text

            content_type = ""
            ct_elem = prop.find("d:getcontenttype", _DAV_NS)
            if ct_elem is not None and ct_elem.text:
                content_type = ct_elem.text

            name = os.path.basename(item_path.rstrip("/")) or item_path

            results.append(FileInfo(
                name=name,
                path=item_path,
                is_dir=is_dir,
                size=size,
                modified=modified,
                content_type=content_type,
            ))

        results.sort(key=lambda f: (not f.is_dir, f.name.lower()))
        logger.debug(f"WebDAV parse_multistatus: {len(results)} items from {request_path}")
        return results

    @staticmethod
    def _ssl_context(verify_ssl: bool = False) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
