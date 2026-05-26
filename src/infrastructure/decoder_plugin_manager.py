import json
import os
import shutil
import hashlib
import ssl
import threading
from typing import Dict, List, Optional

from src.utils.constants import (
    BASS_PLUGINS_DIR, DECODER_REGISTRY_PATH, BASS_PLUGIN_REGISTRY,
    CORE_AUDIO_FORMATS,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

PLUGIN_REPO_URL = "https://raw.githubusercontent.com/musicpp/bass-plugins/main/registry.json"


class DecoderPluginManager:
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
        self._loaded_plugins: Dict[str, dict] = {}
        self._format_map: Dict[str, str] = {}
        self._bass_engine = None
        self._repo_cache: Optional[List[dict]] = None
        self._initialized = True
        os.makedirs(BASS_PLUGINS_DIR, exist_ok=True)

    def set_bass_engine(self, engine):
        self._bass_engine = engine

    def scan_and_load(self):
        self._loaded_plugins.clear()
        self._format_map.clear()
        for ext in CORE_AUDIO_FORMATS:
            self._format_map[ext] = "bass_core"
        self._load_builtin_plugins()
        self._load_user_plugins()
        self._save_registry()
        logger.info(f"Decoder plugins loaded: {len(self._loaded_plugins)} plugins, "
                     f"{len(self._format_map)} formats supported")

    def _load_builtin_plugins(self):
        infra_dir = os.path.dirname(os.path.abspath(__file__))
        for plugin_id, info in BASS_PLUGIN_REGISTRY.items():
            if not info.get("is_builtin", False):
                continue
            dll_name = info["dll"]
            dll_path = os.path.join(infra_dir, dll_name)
            if os.path.exists(dll_path):
                self._try_load_dll(plugin_id, dll_path, info, is_builtin=True)

    def _load_user_plugins(self):
        if not os.path.isdir(BASS_PLUGINS_DIR):
            return
        dll_ext = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")
        for fname in os.listdir(BASS_PLUGINS_DIR):
            if not fname.lower().endswith(dll_ext):
                continue
            dll_path = os.path.join(BASS_PLUGINS_DIR, fname)
            plugin_id = os.path.splitext(fname)[0].lower()
            info = BASS_PLUGIN_REGISTRY.get(plugin_id, {
                "dll": fname,
                "formats": [],
                "name": fname,
                "description": f"User imported plugin: {fname}",
                "is_builtin": False,
                "is_official": False,
            })
            self._try_load_dll(plugin_id, dll_path, info, is_builtin=False)

        infra_dir = os.path.dirname(os.path.abspath(__file__))
        for plugin_id, info in BASS_PLUGIN_REGISTRY.items():
            if info.get("is_builtin", False):
                continue
            dll_name = info["dll"]
            dll_path = os.path.join(infra_dir, dll_name)
            if os.path.exists(dll_path) and plugin_id not in self._loaded_plugins:
                self._try_load_dll(plugin_id, dll_path, info, is_builtin=False)

    def _try_load_dll(self, plugin_id: str, dll_path: str, info: dict, is_builtin: bool = False):
        if self._bass_engine is None:
            self._register_plugin_info(plugin_id, dll_path, info, is_builtin, loaded=False)
            return
        try:
            handle = self._bass_engine.load_bass_plugin(dll_path)
            if handle:
                self._register_plugin_info(plugin_id, dll_path, info, is_builtin, loaded=True)
                logger.info(f"Loaded BASS plugin: {plugin_id} from {dll_path}")
            else:
                self._register_plugin_info(plugin_id, dll_path, info, is_builtin, loaded=False)
                logger.debug(f"Failed to load BASS plugin: {plugin_id} from {dll_path}")
        except Exception as e:
            self._register_plugin_info(plugin_id, dll_path, info, is_builtin, loaded=False)
            logger.warning(f"Error loading BASS plugin {plugin_id}: {e}")

    def _register_plugin_info(self, plugin_id: str, dll_path: str, info: dict,
                               is_builtin: bool, loaded: bool):
        self._loaded_plugins[plugin_id] = {
            "id": plugin_id,
            "dll": info.get("dll", os.path.basename(dll_path)),
            "dll_path": dll_path,
            "formats": info.get("formats", []),
            "name": info.get("name", plugin_id),
            "description": info.get("description", ""),
            "is_builtin": is_builtin,
            "is_official": info.get("is_official", False),
            "loaded": loaded,
            "installed": True,
        }
        if loaded:
            for ext in info.get("formats", []):
                self._format_map[ext] = plugin_id

    def can_play(self, ext: str) -> bool:
        return ext.lower() in self._format_map

    def get_plugin_for_format(self, ext: str) -> Optional[str]:
        return self._format_map.get(ext.lower())

    def get_supported_formats(self) -> List[str]:
        return list(self._format_map.keys())

    def get_all_plugin_info(self) -> List[dict]:
        result = []
        for plugin_id, info in BASS_PLUGIN_REGISTRY.items():
            if plugin_id in self._loaded_plugins:
                result.append(self._loaded_plugins[plugin_id].copy())
            else:
                dll_name = info.get("dll", "")
                dll_exists = False
                if dll_name:
                    infra_dir = os.path.dirname(os.path.abspath(__file__))
                    dll_exists = os.path.exists(os.path.join(infra_dir, dll_name)) or \
                                 os.path.exists(os.path.join(BASS_PLUGINS_DIR, dll_name))
                result.append({
                    "id": plugin_id,
                    "dll": dll_name,
                    "formats": info.get("formats", []),
                    "name": info.get("name", plugin_id),
                    "description": info.get("description", ""),
                    "is_builtin": info.get("is_builtin", False),
                    "is_official": info.get("is_official", False),
                    "loaded": False,
                    "installed": dll_exists,
                })
        for pid, info in self._loaded_plugins.items():
            if pid not in BASS_PLUGIN_REGISTRY:
                result.append(info.copy())
        return result

    def get_installed_plugins(self) -> List[dict]:
        return [p for p in self.get_all_plugin_info()
                if p.get("installed") or p.get("is_builtin")]

    def get_available_plugins(self) -> List[dict]:
        return [p for p in self.get_all_plugin_info()
                if not p.get("installed") and not p.get("is_builtin")]

    def import_plugin(self, file_path: str) -> bool:
        if not os.path.exists(file_path):
            return False
        fname = os.path.basename(file_path)
        dll_ext = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")
        if not fname.lower().endswith(dll_ext):
            logger.warning(f"Invalid plugin file: {fname}")
            return False
        dest = os.path.join(BASS_PLUGINS_DIR, fname)
        try:
            os.makedirs(BASS_PLUGINS_DIR, exist_ok=True)
            shutil.copy2(file_path, dest)
            plugin_id = os.path.splitext(fname)[0].lower()
            info = BASS_PLUGIN_REGISTRY.get(plugin_id, {
                "dll": fname,
                "formats": [],
                "name": fname,
                "description": f"User imported: {fname}",
                "is_builtin": False,
                "is_official": False,
            })
            self._try_load_dll(plugin_id, dest, info, is_builtin=False)
            self._save_registry()
            return True
        except Exception as e:
            logger.error(f"Failed to import plugin {file_path}: {e}")
            return False

    def remove_plugin(self, plugin_id: str) -> bool:
        if plugin_id not in self._loaded_plugins:
            return False
        info = self._loaded_plugins[plugin_id]
        if info.get("is_builtin", False):
            logger.warning(f"Cannot remove builtin plugin: {plugin_id}")
            return False
        dll_path = info.get("dll_path", "")
        if dll_path and os.path.exists(dll_path):
            bass_dir = os.path.dirname(os.path.abspath(__file__))
            if os.path.dirname(dll_path) == bass_dir:
                logger.warning(f"Cannot remove plugin from infrastructure dir: {plugin_id}")
                return False
        try:
            if dll_path and os.path.exists(dll_path):
                os.remove(dll_path)
            for ext in info.get("formats", []):
                self._format_map.pop(ext, None)
            del self._loaded_plugins[plugin_id]
            self._save_registry()
            logger.info(f"Removed decoder plugin: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove plugin {plugin_id}: {e}")
            return False

    def download_plugin(self, plugin_id: str) -> bool:
        if plugin_id not in BASS_PLUGIN_REGISTRY:
            logger.warning(f"Unknown plugin: {plugin_id}")
            return False
        info = BASS_PLUGIN_REGISTRY[plugin_id]
        dll_name = info["dll"]
        repo_data = self._fetch_repo_data()
        download_url = None
        sha256 = None
        for item in repo_data:
            if item.get("id") == plugin_id:
                download_url = item.get("download_url")
                sha256 = item.get("sha256")
                break
        if not download_url:
            download_url = info.get("download_url", "")
        if not download_url:
            download_url = f"https://www.un4seen.com/files/{dll_name}"
        try:
            import urllib.request
            import tempfile
            import zipfile
            os.makedirs(BASS_PLUGINS_DIR, exist_ok=True)
            is_zip = download_url.lower().endswith(".zip")
            logger.info(f"Downloading decoder plugin: {plugin_id} from {download_url}")
            ssl_ctx = self._create_ssl_context()
            if is_zip:
                tmp_dir = tempfile.mkdtemp(prefix="musicpp_")
                zip_path = os.path.join(tmp_dir, os.path.basename(download_url))
                try:
                    with urllib.request.urlopen(download_url, context=ssl_ctx) as resp, open(zip_path, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    if sha256:
                        actual = self._sha256_file(zip_path)
                        if actual != sha256:
                            logger.error(f"SHA256 mismatch for {dll_name}: expected {sha256}, got {actual}")
                            return False
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        is_64bit = sys.maxsize > 2 ** 32
                        arch_dir = "x64/" if is_64bit else ""
                        dll_found = None
                        dll_root = None
                        for member in zf.namelist():
                            lower = member.lower()
                            if lower.endswith(".dll") and not lower.endswith("/"):
                                basename = os.path.basename(member)
                                if basename.lower() == dll_name.lower():
                                    parent = os.path.dirname(member).replace("\\", "/").lower()
                                    if parent == arch_dir.rstrip("/"):
                                        dll_found = member
                                        break
                                    elif not parent or parent == ".":
                                        dll_root = member
                        if dll_found is None:
                            dll_found = dll_root
                        if dll_found is None:
                            for member in zf.namelist():
                                lower = member.lower()
                                if lower.endswith(".dll") and not lower.endswith("/"):
                                    parent = os.path.dirname(member).replace("\\", "/").lower()
                                    if arch_dir and parent == arch_dir.rstrip("/"):
                                        dll_found = member
                                        break
                                    elif not arch_dir and not parent:
                                        dll_found = member
                                        break
                        if dll_found is None:
                            for member in zf.namelist():
                                lower = member.lower()
                                if lower.endswith(".dll") and not lower.endswith("/"):
                                    dll_found = member
                                    break
                        if dll_found is None:
                            logger.error(f"No DLL found in ZIP: {download_url}")
                            return False
                        dest = os.path.join(BASS_PLUGINS_DIR, dll_name)
                        with zf.open(dll_found) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                        logger.info(f"Extracted {dll_found} -> {dest} (arch={'x64' if is_64bit else 'x86'})")
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                dest = os.path.join(BASS_PLUGINS_DIR, dll_name)
                with urllib.request.urlopen(download_url, context=ssl_ctx) as resp, open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
                if sha256:
                    actual = self._sha256_file(dest)
                    if actual != sha256:
                        logger.error(f"SHA256 mismatch for {dll_name}: expected {sha256}, got {actual}")
                        os.remove(dest)
                        return False
            self._try_load_dll(plugin_id, dest, info, is_builtin=False)
            self._save_registry()
            logger.info(f"Downloaded and loaded decoder plugin: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to download plugin {plugin_id}: {e}")
            return False

    def _fetch_repo_data(self) -> List[dict]:
        if self._repo_cache is not None:
            return self._repo_cache
        try:
            import urllib.request
            ssl_ctx = self._create_ssl_context()
            req = urllib.request.Request(PLUGIN_REPO_URL, headers={"User-Agent": "MusicPP/1.0"})
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._repo_cache = data.get("plugins", [])
                return self._repo_cache
        except Exception as e:
            logger.warning(f"Failed to fetch plugin repo: {e}")
            return []

    @staticmethod
    def _create_ssl_context():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @staticmethod
    def _sha256_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _save_registry(self):
        try:
            data = {}
            for pid, info in self._loaded_plugins.items():
                data[pid] = {
                    "dll": info.get("dll", ""),
                    "name": info.get("name", ""),
                    "formats": info.get("formats", []),
                    "loaded": info.get("loaded", False),
                    "is_builtin": info.get("is_builtin", False),
                }
            os.makedirs(os.path.dirname(DECODER_REGISTRY_PATH), exist_ok=True)
            with open(DECODER_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save decoder registry: {e}")

    def find_missing_plugin(self, ext: str) -> Optional[dict]:
        ext = ext.lower()
        if ext in self._format_map:
            return None
        for plugin_id, info in BASS_PLUGIN_REGISTRY.items():
            if ext in info.get("formats", []):
                return {"id": plugin_id, **info}
        return None


import sys
