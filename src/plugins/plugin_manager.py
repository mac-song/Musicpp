import importlib.util
import os
import sys
import threading
from typing import Any, Dict, List, Optional, Type

from src.core.database_service import DatabaseService
from src.core.event_bus import EventBus
from src.utils.constants import EVENT_PLUGIN_STATUS_CHANGED
from src.utils.logger import setup_logger
from .plugin_interface import MusicPluginInterface

logger = setup_logger(__name__)

PLUGINS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "plugins")


class PluginManager:
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
        self._db = DatabaseService()
        self._event_bus = EventBus()
        self._plugins: Dict[str, MusicPluginInterface] = {}
        self._plugin_status: Dict[str, str] = {}
        self._initialized = True
        self._auto_load()

    def _auto_load(self):
        if os.path.isdir(PLUGINS_DIR):
            self.load_plugins_from_directory(PLUGINS_DIR)

    def load_plugin(self, plugin_path: str) -> bool:
        try:
            if not os.path.exists(plugin_path):
                logger.error(f"Plugin file not found: {plugin_path}")
                return False

            plugin_name = os.path.splitext(os.path.basename(plugin_path))[0]

            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to load plugin spec: {plugin_path}")
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_name] = module
            spec.loader.exec_module(module)

            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, MusicPluginInterface) and
                    attr is not MusicPluginInterface):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.error(f"No plugin class found in: {plugin_path}")
                return False

            plugin_instance = plugin_class()
            pid = plugin_instance.plugin_id

            self._plugins[pid] = plugin_instance
            self._plugin_status[pid] = "enabled"

            self._save_plugin_to_db(plugin_instance, plugin_path)

            self._event_bus.publish(EVENT_PLUGIN_STATUS_CHANGED, {
                "plugin": pid,
                "status": "enabled"
            })

            logger.info(f"Plugin loaded: {plugin_instance.name} v{plugin_instance.version} ({pid})")
            return True

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_path}: {e}")
            return False

    def unload_plugin(self, plugin_id: str) -> bool:
        if plugin_id not in self._plugins:
            return False

        del self._plugins[plugin_id]
        self._plugin_status[plugin_id] = "disabled"

        self._event_bus.publish(EVENT_PLUGIN_STATUS_CHANGED, {
            "plugin": plugin_id,
            "status": "disabled"
        })

        logger.info(f"Plugin unloaded: {plugin_id}")
        return True

    def enable_plugin(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            self._plugin_status[plugin_id] = "enabled"
            self._event_bus.publish(EVENT_PLUGIN_STATUS_CHANGED, {
                "plugin": plugin_id,
                "status": "enabled"
            })
            return True
        return False

    def disable_plugin(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            self._plugin_status[plugin_id] = "disabled"
            self._event_bus.publish(EVENT_PLUGIN_STATUS_CHANGED, {
                "plugin": plugin_id,
                "status": "disabled"
            })
            return True
        return False

    def delete_plugin(self, plugin_id: str) -> bool:
        if plugin_id not in self._plugins:
            return False
        if self._plugin_status.get(plugin_id) != "disabled":
            return False
        del self._plugins[plugin_id]
        if plugin_id in self._plugin_status:
            del self._plugin_status[plugin_id]
        self._db.delete("plugin", "name = ?", (plugin_id,))
        self._event_bus.publish(EVENT_PLUGIN_STATUS_CHANGED, {
            "plugin": plugin_id,
            "status": "deleted"
        })
        logger.info(f"Plugin deleted (soft): {plugin_id}")
        return True

    def get_plugin(self, plugin_id: str) -> Optional[MusicPluginInterface]:
        plugin = self._plugins.get(plugin_id)
        if plugin and self._plugin_status.get(plugin_id) == "enabled":
            return plugin
        return None

    def get_all_plugins(self) -> Dict[str, MusicPluginInterface]:
        return {
            pid: plugin
            for pid, plugin in self._plugins.items()
            if self._plugin_status.get(pid) == "enabled"
        }

    def get_plugin_info(self, plugin_id: str) -> Optional[Dict]:
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return None

        source_map = {
            "kg": "官方API+第三方",
            "kugou": "MusicDL第三方",
            "kugou_api": "官方API+第三方",
            "wy": "官方API+第三方",
            "lx_api": "洛雪",
            "kuwo": "MusicDL第三方",
            "qq": "MusicDL第三方",
            "xm": "MusicDL第三方",
        }

        source_name = plugin.meta.get("source_name", "")
        if not source_name and "." in plugin_id:
            prefix = plugin_id.split(".")[0]
            source_name = source_map.get(prefix, prefix)
        elif not source_name:
            source_name = source_map.get(plugin_id, "")

        return {
            "id": plugin_id,
            "name": plugin.name,
            "source_name": source_name,
            "version": plugin.version,
            "author": plugin.author,
            "description": plugin.meta.get("description", ""),
            "status": self._plugin_status.get(plugin_id, "enabled"),
            "config_schema": plugin.meta.get("config_schema", {}),
            "can_search": getattr(plugin, "can_search", True),
            "can_play": getattr(plugin, "can_play", True),
            "can_download": getattr(plugin, "can_download", True),
            "can_get_url": getattr(plugin, "can_get_url", True),
        }

    def get_all_plugin_info(self) -> List[Dict]:
        return [
            info for info in (
                self.get_plugin_info(pid)
                for pid in self._plugins.keys()
            ) if info is not None
        ]

    def search_all(self, keyword: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        all_results = []
        total = 0
        for pid, plugin in self.get_all_plugins().items():
            try:
                result = plugin.search(keyword, page, limit)
                if isinstance(result, dict):
                    all_results.extend(result.get("list", []))
                    total += result.get("total", 0)
                elif isinstance(result, list):
                    all_results.extend(result)
                    total += len(result)
            except Exception as e:
                logger.warning(f"Plugin {pid} search failed: {e}")
                continue
        return {"total": total, "list": all_results}

    def _save_plugin_to_db(self, plugin: MusicPluginInterface, path: str) -> None:
        existing = self._db.fetchone(
            "SELECT id FROM plugin WHERE name = ?",
            (plugin.plugin_id,)
        )

        data = {
            "name": plugin.plugin_id,
            "type": "music",
            "path": path,
            "version": plugin.version,
            "status": "enabled"
        }

        if existing:
            self._db.update("plugin", data, "name = ?", (plugin.plugin_id,))
        else:
            self._db.insert("plugin", data)

    def load_plugins_from_directory(self, directory: str) -> int:
        if not os.path.exists(directory):
            return 0

        count = 0
        for file in os.listdir(directory):
            if file.endswith(".py") and not file.startswith("__"):
                plugin_path = os.path.join(directory, file)
                if self.load_plugin(plugin_path):
                    count += 1

        return count

    def import_from_export_folder(self, export_root: str) -> dict:
        import json as _json
        import shutil as _shutil

        results = {
            "source": {"success": 0, "failed": 0, "details": []},
            "decoder": {"success": 0, "failed": 0, "details": []},
            "transcription": {"success": 0, "failed": 0, "details": []},
            "tool": {"success": 0, "failed": 0, "details": []},
            "dictionary": {"success": 0, "failed": 0, "details": []},
            "alist": {"success": 0, "failed": 0, "details": []},
            "whisper": {"success": 0, "failed": 0, "details": []},
        }

        source_dir = os.path.join(export_root, "音源插件")
        if os.path.isdir(source_dir):
            manifest_path = os.path.join(source_dir, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = _json.load(f)
                    for plugin_info in manifest.get("plugins", []):
                        src_file = os.path.join(source_dir, plugin_info["file"])
                        if os.path.exists(src_file):
                            dest_dir = PLUGINS_DIR
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_file = os.path.join(dest_dir, plugin_info["file"])
                            _shutil.copy2(src_file, dest_file)
                            if self.load_plugin(dest_file):
                                results["source"]["success"] += 1
                                results["source"]["details"].append(f"✓ {plugin_info['name']}")
                            else:
                                results["source"]["failed"] += 1
                                results["source"]["details"].append(f"✗ {plugin_info['name']} (加载失败)")
                        else:
                            results["source"]["failed"] += 1
                            results["source"]["details"].append(f"✗ {plugin_info['name']} (文件不存在)")
                except Exception as e:
                    results["source"]["failed"] += 1
                    results["source"]["details"].append(f"✗ manifest.json 解析失败: {e}")
            else:
                for file in os.listdir(source_dir):
                    if file.endswith(".py") and not file.startswith("__"):
                        src_file = os.path.join(source_dir, file)
                        dest_dir = PLUGINS_DIR
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_file = os.path.join(dest_dir, file)
                        _shutil.copy2(src_file, dest_file)
                        if self.load_plugin(dest_file):
                            results["source"]["success"] += 1
                            results["source"]["details"].append(f"✓ {file}")
                        else:
                            results["source"]["failed"] += 1
                            results["source"]["details"].append(f"✗ {file} (加载失败)")

        decoder_dir = os.path.join(export_root, "音频解码插件")
        if os.path.isdir(decoder_dir):
            from src.utils.constants import BASS_PLUGINS_DIR, BASE_DIR
            os.makedirs(BASS_PLUGINS_DIR, exist_ok=True)
            infra_dir = os.path.join(BASE_DIR, "infrastructure")
            os.makedirs(infra_dir, exist_ok=True)

            manifest_path = os.path.join(decoder_dir, "manifest.json")
            core_dlls = set()
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = _json.load(f)
                    for plugin_info in manifest.get("plugins", []):
                        if plugin_info.get("is_core"):
                            core_dlls.add(plugin_info["file"])
                except Exception:
                    pass

            from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
            dpm = DecoderPluginManager()
            for file in os.listdir(decoder_dir):
                if not file.lower().endswith(".dll"):
                    continue
                src_file = os.path.join(decoder_dir, file)
                if file in core_dlls:
                    dest = os.path.join(infra_dir, file)
                    try:
                        _shutil.copy2(src_file, dest)
                        results["decoder"]["success"] += 1
                        results["decoder"]["details"].append(f"✓ {file} (核心库)")
                    except Exception as e:
                        results["decoder"]["failed"] += 1
                        results["decoder"]["details"].append(f"✗ {file} ({e})")
                else:
                    if dpm.import_plugin(src_file):
                        results["decoder"]["success"] += 1
                        results["decoder"]["details"].append(f"✓ {file}")
                    else:
                        dest = os.path.join(BASS_PLUGINS_DIR, file)
                        try:
                            _shutil.copy2(src_file, dest)
                            results["decoder"]["success"] += 1
                            results["decoder"]["details"].append(f"✓ {file} (已复制)")
                        except Exception as e:
                            results["decoder"]["failed"] += 1
                            results["decoder"]["details"].append(f"✗ {file} ({e})")

        transcription_dir = os.path.join(export_root, "转录插件")
        if os.path.isdir(transcription_dir):
            from src.utils.constants import BASE_DIR
            plugins_dest = os.path.join(BASE_DIR, "plugins")
            os.makedirs(plugins_dest, exist_ok=True)
            for file in os.listdir(transcription_dir):
                if file.endswith(".py") and not file.startswith("__"):
                    src_file = os.path.join(transcription_dir, file)
                    dest_file = os.path.join(plugins_dest, file)
                    try:
                        _shutil.copy2(src_file, dest_file)
                        results["transcription"]["success"] += 1
                        results["transcription"]["details"].append(f"✓ {file}")
                    except Exception as e:
                        results["transcription"]["failed"] += 1
                        results["transcription"]["details"].append(f"✗ {file} ({e})")

        tool_dir = os.path.join(export_root, "工具")
        if os.path.isdir(tool_dir):
            from src.utils.constants import ROOT_DIR
            ffmpeg_dest = os.path.join(ROOT_DIR, "plugins", "ffmpeg")
            os.makedirs(ffmpeg_dest, exist_ok=True)
            for file in os.listdir(tool_dir):
                if file.endswith(".exe"):
                    src_file = os.path.join(tool_dir, file)
                    dest_file = os.path.join(ffmpeg_dest, file)
                    try:
                        _shutil.copy2(src_file, dest_file)
                        results["tool"]["success"] += 1
                        results["tool"]["details"].append(f"✓ {file}")
                    except Exception as e:
                        results["tool"]["failed"] += 1
                        results["tool"]["details"].append(f"✗ {file} ({e})")

        dict_dir = os.path.join(export_root, "字典数据")
        if os.path.isdir(dict_dir):
            from src.utils.constants import CACHE_DIR
            ecdict_dest = os.path.join(CACHE_DIR, "ecdict")
            os.makedirs(ecdict_dest, exist_ok=True)
            for file in os.listdir(dict_dir):
                if file.endswith(".db"):
                    src_file = os.path.join(dict_dir, file)
                    dest_file = os.path.join(ecdict_dest, file)
                    try:
                        _shutil.copy2(src_file, dest_file)
                        results["dictionary"]["success"] += 1
                        results["dictionary"]["details"].append(f"✓ {file}")
                    except Exception as e:
                        results["dictionary"]["failed"] += 1
                        results["dictionary"]["details"].append(f"✗ {file} ({e})")

        alist_dir = os.path.join(export_root, "AList服务")
        if os.path.isdir(alist_dir):
            from src.utils.constants import ROOT_DIR
            for file in os.listdir(alist_dir):
                if file.endswith(".exe"):
                    src_file = os.path.join(alist_dir, file)
                    dest_file = os.path.join(ROOT_DIR, file)
                    try:
                        _shutil.copy2(src_file, dest_file)
                        results["alist"]["success"] += 1
                        results["alist"]["details"].append(f"✓ {file}")
                    except Exception as e:
                        results["alist"]["failed"] += 1
                        results["alist"]["details"].append(f"✗ {file} ({e})")

        whisper_dir = os.path.join(export_root, "Whisper")
        if os.path.isdir(whisper_dir):
            manifest_path = os.path.join(whisper_dir, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = _json.load(f)
                    for plugin_info in manifest.get("plugins", []):
                        pid = plugin_info.get("id", "")
                        if pid == "faster_whisper_pip":
                            pip_dir = os.path.join(whisper_dir, plugin_info.get("pip_dir", "pip_packages"))
                            if os.path.isdir(pip_dir):
                                try:
                                    import subprocess as _subprocess
                                    cmd = [
                                        sys.executable, "-m", "pip", "install",
                                        "--no-index",
                                        f"--find-links={pip_dir}",
                                        "faster-whisper",
                                    ]
                                    proc = _subprocess.run(
                                        cmd,
                                        capture_output=True, text=True, timeout=300,
                                    )
                                    if proc.returncode == 0:
                                        results["whisper"]["success"] += 1
                                        results["whisper"]["details"].append(f"✓ faster-whisper pip包离线安装成功")
                                    else:
                                        results["whisper"]["failed"] += 1
                                        err_msg = proc.stderr.strip().split("\n")[-1] if proc.stderr else "未知错误"
                                        results["whisper"]["details"].append(f"✗ faster-whisper pip包安装失败: {err_msg}")
                                except Exception as e:
                                    results["whisper"]["failed"] += 1
                                    results["whisper"]["details"].append(f"✗ faster-whisper pip包安装异常: {e}")
                            else:
                                results["whisper"]["failed"] += 1
                                results["whisper"]["details"].append(f"✗ pip_packages 目录不存在")

                        elif pid == "whisper_model_base_en":
                            model_dir_name = None
                            for item in os.listdir(whisper_dir):
                                if item.startswith("models--"):
                                    model_dir_name = item
                                    break
                            if model_dir_name:
                                src_model = os.path.join(whisper_dir, model_dir_name)
                                hf_cache = os.path.join(
                                    os.path.expanduser("~"), ".cache",
                                    "huggingface", "hub",
                                )
                                os.makedirs(hf_cache, exist_ok=True)
                                dest_model = os.path.join(hf_cache, model_dir_name)
                                try:
                                    if os.path.exists(dest_model):
                                        _shutil.rmtree(dest_model)
                                    _shutil.copytree(src_model, dest_model)
                                    results["whisper"]["success"] += 1
                                    results["whisper"]["details"].append(f"✓ {plugin_info.get('name', model_dir_name)} 模型缓存已复制")
                                except Exception as e:
                                    results["whisper"]["failed"] += 1
                                    results["whisper"]["details"].append(f"✗ 模型缓存复制失败: {e}")
                            else:
                                results["whisper"]["failed"] += 1
                                results["whisper"]["details"].append(f"✗ 模型目录不存在")
                except Exception as e:
                    results["whisper"]["failed"] += 1
                    results["whisper"]["details"].append(f"✗ Whisper manifest.json 解析失败: {e}")
            else:
                pip_dir = os.path.join(whisper_dir, "pip_packages")
                if os.path.isdir(pip_dir):
                    try:
                        import subprocess as _subprocess
                        cmd = [
                            sys.executable, "-m", "pip", "install",
                            "--no-index",
                            f"--find-links={pip_dir}",
                            "faster-whisper",
                        ]
                        proc = _subprocess.run(
                            cmd,
                            capture_output=True, text=True, timeout=300,
                        )
                        if proc.returncode == 0:
                            results["whisper"]["success"] += 1
                            results["whisper"]["details"].append(f"✓ faster-whisper pip包离线安装成功")
                        else:
                            results["whisper"]["failed"] += 1
                            err_msg = proc.stderr.strip().split("\n")[-1] if proc.stderr else "未知错误"
                            results["whisper"]["details"].append(f"✗ faster-whisper pip包安装失败: {err_msg}")
                    except Exception as e:
                        results["whisper"]["failed"] += 1
                        results["whisper"]["details"].append(f"✗ faster-whisper pip包安装异常: {e}")

                for item in os.listdir(whisper_dir):
                    if item.startswith("models--"):
                        src_model = os.path.join(whisper_dir, item)
                        hf_cache = os.path.join(
                            os.path.expanduser("~"), ".cache",
                            "huggingface", "hub",
                        )
                        os.makedirs(hf_cache, exist_ok=True)
                        dest_model = os.path.join(hf_cache, item)
                        try:
                            if os.path.exists(dest_model):
                                _shutil.rmtree(dest_model)
                            _shutil.copytree(src_model, dest_model)
                            results["whisper"]["success"] += 1
                            results["whisper"]["details"].append(f"✓ {item} 模型缓存已复制")
                        except Exception as e:
                            results["whisper"]["failed"] += 1
                            results["whisper"]["details"].append(f"✗ 模型缓存复制失败: {e}")

        return results
