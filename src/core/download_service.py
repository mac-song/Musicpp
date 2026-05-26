import os
import threading
import time
import uuid

from PySide6.QtCore import QObject, Signal, QTimer

from src.core.network_service import NetworkService
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class DownloadService(QObject):
    task_added = Signal(dict)
    task_progress = Signal(str, int, int)
    task_completed = Signal(str, str)
    task_failed = Signal(str, str)
    task_status_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._network = NetworkService()
        self._tasks: dict = {}
        self._queue: list = []
        self._active_count = 0
        self._max_concurrent = 3
        self._lock = threading.Lock()
        self._default_save_path = os.path.expanduser("~/Music/Downloads")
        self._cancel_flags: dict = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._process_queue)

    def _get_download_url_fallback(self, song_data: dict, quality: str) -> str:
        """尝试多种方式获取下载URL - 在后台线程中调用"""
        import requests

        plugin_id = song_data.get("pluginId", "")
        song_id = song_data.get("id", "") or song_data.get("hash", "") or song_data.get("songmid", "")

        # 如果有插件，优先使用插件
        if plugin_id:
            try:
                plugin_manager = __import__("src.plugins.plugin_manager", fromlist=["PluginManager"]).PluginManager()
                plugin = plugin_manager.get_plugin(plugin_id)
                if plugin:
                    result = plugin.get_song_url(song_id, quality)
                    if isinstance(result, dict):
                        url = result.get("url", "")
                        if url and url.startswith("http"):
                            return url
            except Exception as e:
                logger.warning(f"Plugin URL fetch failed: {e}")

        return ""

    def add_task(self, song_data: dict, quality: str, save_path: str = "") -> str:
        task_id = str(uuid.uuid4())

        if not save_path:
            save_path = self._default_save_path

        artist = song_data.get("artist") or song_data.get("singer", "Unknown")
        title = song_data.get("title") or song_data.get("name", "Unknown")
        filename = f"{artist} - {title}.mp3"
        filename = "".join(c for c in filename if c not in r'\/:*?"<>|').strip()
        file_path = os.path.join(save_path, filename)

        task = {
            "task_id": task_id,
            "id": task_id,
            "song": song_data,
            "title": title,
            "artist": artist,
            "quality": quality,
            "url": "",
            "path": file_path,
            "progress": 0,
            "speed": 0,
            "size": 0,
            "downloaded": 0,
            "status": "pending",
            "error": "",
            "created_at": time.time(),
            "completed_at": 0.0
        }

        with self._lock:
            self._tasks[task_id] = task
            self._cancel_flags[task_id] = threading.Event()

        self.task_added.emit(task)
        self.task_status_changed.emit(task_id, "pending")

        return task_id

    def pause_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task["status"] == "downloading":
                self._cancel_flags.get(task_id, threading.Event()).set()
                task["status"] = "pending"
                task["speed"] = 0
                self.task_status_changed.emit(task_id, "pending")
            elif task["status"] == "queued":
                task["status"] = "pending"
                if task_id in self._queue:
                    self._queue.remove(task_id)
                self.task_status_changed.emit(task_id, "pending")

    def resume_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task["status"] in ("pending", "failed"):
                task["status"] = "pending"
                task["error"] = ""
                self._cancel_flags[task_id] = threading.Event()
                self.task_status_changed.emit(task_id, "pending")
                self._enqueue_task(task_id)

    def cancel_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task["status"] == "downloading":
                self._cancel_flags.get(task_id, threading.Event()).set()
                task["status"] = "canceled"
                task["speed"] = 0
            else:
                task["status"] = "canceled"
                if task_id in self._queue:
                    self._queue.remove(task_id)

        self.task_status_changed.emit(task_id, "canceled")

    def remove_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task["status"] == "downloading":
                self._cancel_flags.get(task_id, threading.Event()).set()
            if task_id in self._queue:
                self._queue.remove(task_id)
            del self._tasks[task_id]
            if task_id in self._cancel_flags:
                del self._cancel_flags[task_id]

    def get_all_tasks(self) -> list:
        with self._lock:
            return list(self._tasks.values())

    def get_task(self, task_id: str) -> dict:
        with self._lock:
            return self._tasks.get(task_id)

    def start_queue(self):
        if not self._timer.isActive():
            self._timer.start(500)
        self._process_queue()

    def _enqueue_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if not task:
            return
        if task["status"] == "pending" and task_id not in self._queue:
            task["status"] = "queued"
            self._queue.append(task_id)
            self.task_status_changed.emit(task_id, "queued")

    def _process_queue(self):
        to_start = []
        with self._lock:
            pending_tasks = [
                tid for tid, task in self._tasks.items()
                if task["status"] == "pending"
            ]
            for tid in pending_tasks:
                self._enqueue_task(tid)

            while self._active_count < self._max_concurrent and self._queue:
                task_id = self._queue.pop(0)
                task = self._tasks.get(task_id)
                if not task or task["status"] != "queued":
                    continue
                self._active_count += 1
                task["status"] = "downloading"
                to_start.append(task_id)

        for task_id in to_start:
            self.task_status_changed.emit(task_id, "downloading")
            thread = threading.Thread(
                target=self._download_worker,
                args=(task_id,),
                daemon=True
            )
            thread.start()

    def _download_worker(self, task_id: str):
        task = self._tasks.get(task_id)
        if not task:
            with self._lock:
                self._active_count = max(0, self._active_count - 1)
            return

        cancel_flag = self._cancel_flags.get(task_id, threading.Event())

        url = task.get("url", "")
        save_path = task["path"]
        part_path = save_path + ".part"
        song_data = task.get("song", {})
        quality = task.get("quality", "320k")

        if not url:
            logger.info(f"正在获取下载链接: {task.get('title', 'Unknown')}")
            url = self._get_download_url_fallback(song_data, quality)
            if url:
                task["url"] = url
            else:
                with self._lock:
                    task["status"] = "failed"
                    task["error"] = "无法获取下载链接"
                    self._active_count = max(0, self._active_count - 1)
                self.task_failed.emit(task_id, "无法获取下载链接")
                self.task_status_changed.emit(task_id, "failed")
                return

        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            headers = {}
            downloaded = 0

            if os.path.exists(part_path):
                downloaded = os.path.getsize(part_path)
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"
                    task["downloaded"] = downloaded

            start_time = time.time()
            last_downloaded = downloaded
            last_time = start_time

            request_headers = headers if headers else None

            session = self._network._session
            request_headers_full = dict(session.headers)
            if request_headers:
                request_headers_full.update(request_headers)

            response = session.get(
                url,
                headers=request_headers_full,
                timeout=30,
                stream=True
            )

            if response.status_code == 416:
                if os.path.exists(part_path):
                    os.remove(part_path)
                downloaded = 0
                del headers["Range"]
                request_headers_full = dict(session.headers)
                response = session.get(url, headers=request_headers_full, timeout=30, stream=True)

            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            if downloaded > 0 and response.status_code == 206:
                content_range = response.headers.get("content-range", "")
                if "/" in content_range:
                    total_size = int(content_range.split("/")[-1])
            elif downloaded > 0 and response.status_code == 200:
                downloaded = 0
                task["downloaded"] = 0

            if total_size > 0:
                task["size"] = total_size

            chunk_size = 8192
            mode = "ab" if downloaded > 0 and response.status_code == 206 else "wb"

            with open(part_path, mode) as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if cancel_flag.is_set():
                        with self._lock:
                            task["status"] = "canceled"
                            task["speed"] = 0
                            self._active_count = max(0, self._active_count - 1)
                        self.task_status_changed.emit(task_id, "canceled")
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        task["downloaded"] = downloaded

                        current_time = time.time()
                        elapsed = current_time - last_time
                        if elapsed >= 0.5:
                            speed = int((downloaded - last_downloaded) / elapsed)
                            task["speed"] = speed
                            last_downloaded = downloaded
                            last_time = current_time

                        if total_size > 0:
                            progress = int(downloaded / total_size * 100)
                            task["progress"] = progress
                            self.task_progress.emit(task_id, progress, task["speed"])
                        else:
                            task["progress"] = 0

            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(part_path, save_path)

            with self._lock:
                task["status"] = "completed"
                task["progress"] = 100
                task["speed"] = 0
                task["completed_at"] = time.time()
                self._active_count = max(0, self._active_count - 1)

            self.task_completed.emit(task_id, save_path)
            self.task_status_changed.emit(task_id, "completed")

        except Exception as e:
            logger.error(f"Download failed for task {task_id}: {e}")

            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except Exception:
                pass

            with self._lock:
                task["status"] = "failed"
                task["error"] = str(e)
                task["speed"] = 0
                self._active_count = max(0, self._active_count - 1)

            self.task_failed.emit(task_id, str(e))
            self.task_status_changed.emit(task_id, "failed")
