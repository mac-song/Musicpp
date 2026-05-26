import json
import os
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

from src.core.music_library_service import MusicLibraryService
from src.utils.constants import CONFIG_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

BEETS_CONFIG_DIR = os.path.join(CONFIG_DIR, "beets")
BEETS_CONFIG_PATH = os.path.join(BEETS_CONFIG_DIR, "config.yaml")
BEETS_DB_PATH = os.path.join(BEETS_CONFIG_DIR, "library.db")
BEETS_STATE_PATH = os.path.join(BEETS_CONFIG_DIR, "state.pickle")


class BeetsService:
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
        self._music_library = MusicLibraryService()
        self._initialized = True

    def is_installed(self) -> bool:
        try:
            import beets
            return True
        except ImportError:
            return False

    def install(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        mirror_url: str = "",
    ) -> bool:
        try:
            if progress_callback:
                progress_callback("准备安装 Beets + lastgenre...", 5)

            packages = ["beets", "pylast"]
            cmd = [sys.executable, "-m", "pip", "install"] + packages + ["--progress-bar", "off"]
            if mirror_url:
                cmd += ["-i", mirror_url, "--trusted-host", mirror_url.split("//")[-1].split("/")[0]]

            if progress_callback:
                progress_callback("正在下载安装 Beets...", 10)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    logger.info(f"[pip] {line}")
                    clean = line.strip()
                    if clean.startswith("Collecting"):
                        if progress_callback:
                            progress_callback(f"收集依赖: {clean[len('Collecting'):].strip()}", 20)
                    elif clean.startswith("Downloading"):
                        if progress_callback:
                            progress_callback("下载依赖包...", 35)
                    elif clean.startswith("Installing collected"):
                        if progress_callback:
                            progress_callback("正在安装...", 70)
                    elif clean.startswith("Successfully installed"):
                        if progress_callback:
                            progress_callback("安装完成!", 90)

            proc.wait()
            if proc.returncode == 0:
                self._ensure_config()
                if progress_callback:
                    progress_callback("Beets 安装成功!", 100)
                return True
            else:
                logger.error(f"pip install failed with return code {proc.returncode}")
                return False

        except Exception as e:
            logger.error(f"Beets install error: {e}")
            if progress_callback:
                progress_callback(f"安装失败: {e}", 0)
            return False

    def _ensure_config(self):
        os.makedirs(BEETS_CONFIG_DIR, exist_ok=True)

        if not os.path.exists(BEETS_CONFIG_PATH):
            config_lines = [
                "directory: ~/Music",
                f"library: {BEETS_DB_PATH}",
                "",
                "musicbrainz:",
                "    host: musicbrainz.org",
                "    https: true",
                "    ratelimit: 1",
                "    ratelimit_interval: 1",
                "",
                "import:",
                "    move: no",
                "    copy: no",
                "    write: yes",
                "    autotag: yes",
                "    quiet: yes",
                "    timid: no",
                "    quiet_fallback: asis",
                "    none_rec_action: asis",
                "",
                "plugins: lastgenre",
                "lastgenre:",
                "    auto: yes",
                "    force: yes",
                "    source: track",
                "    fallback: Unknown",
                "    whitelist: yes",
                "    min_weight: 10",
                "    count: 1",
                "",
                "paths:",
                "    default: $albumartist/$album%aunique{}/$track $title",
                "    singleton: Non-Album/$artist - $title",
                "    comp: Compilations/$album%aunique{}/$track $title",
            ]
            config_content = "\n".join(config_lines) + "\n"
            with open(BEETS_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(config_content)
            logger.info(f"Created Beets config: {BEETS_CONFIG_PATH}")
        else:
            self._patch_config()

    def _clear_beets_library(self):
        for path in (BEETS_DB_PATH, BEETS_STATE_PATH):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Cleared Beets file: {path}")
            except Exception as e:
                logger.error(f"Clear Beets file error ({path}): {e}")

    def _patch_config(self):
        try:
            with open(BEETS_CONFIG_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            changed = False
            if "autotag: no" in content:
                content = content.replace("autotag: no", "autotag: yes")
                changed = True
            if "timid: yes" in content:
                content = content.replace("timid: yes", "timid: no")
                changed = True
            if "quiet: no" in content:
                content = content.replace("quiet: no", "quiet: yes")
                changed = True
            if "none_rec_action: skip" in content:
                content = content.replace("none_rec_action: skip", "none_rec_action: asis")
                changed = True
            if "quiet_fallback" not in content:
                content = content.replace(
                    "none_rec_action: asis",
                    "none_rec_action: asis\n    quiet_fallback: asis",
                )
                changed = True
            elif "quiet_fallback: skip" in content:
                content = content.replace("quiet_fallback: skip", "quiet_fallback: asis")
                changed = True
            if "musicbrainz:" not in content:
                mb_block = (
                    "musicbrainz:\n"
                    "    host: musicbrainz.org\n"
                    "    https: true\n"
                    "    ratelimit: 1\n"
                    "    ratelimit_interval: 1\n\n"
                )
                content = mb_block + content
                changed = True
            if "host: musicbrainz.tanhoat.org" in content:
                content = content.replace(
                    "host: musicbrainz.tanhoat.org",
                    "host: musicbrainz.org",
                )
                changed = True

            if changed:
                with open(BEETS_CONFIG_PATH, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Patched Beets config for non-interactive mode")
        except Exception as e:
            logger.error(f"Patch config error: {e}")

    def scan_directory(
        self,
        directory: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> bool:
        self._ensure_config()

        try:
            if progress_callback:
                progress_callback(f"正在扫描目录: {directory}", 5)

            self._clear_beets_library()

            env = os.environ.copy()
            env["BEETSDIR"] = BEETS_CONFIG_DIR

            cmd = [
                sys.executable, "-m", "beets",
                "-c", BEETS_CONFIG_PATH,
                "-d", BEETS_CONFIG_DIR,
                "import",
                "-q",
                "-W",
                directory,
            ]

            logger.info(f"Running Beets import: {' '.join(cmd)}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                stdin=subprocess.DEVNULL,
            )

            output_lines = []
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    logger.info(f"[beets] {line}")

            proc.wait(timeout=600)

            if proc.returncode == 0:
                if progress_callback:
                    progress_callback("扫描完成，正在同步分类信息...", 80)
                self._sync_genres_from_beets()
                if progress_callback:
                    progress_callback("分类同步完成!", 100)
                return True
            else:
                tail = "\n".join(output_lines[-10:]) if output_lines else ""
                logger.warning(f"Beets import returned code {proc.returncode}\n{tail}")
                self._sync_genres_from_beets()
                if progress_callback:
                    progress_callback("扫描完成（部分成功）", 90)
                return True

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Beets import timed out")
            if progress_callback:
                progress_callback("扫描超时", 0)
            return False
        except Exception as e:
            logger.error(f"Beets scan error: {e}")
            if progress_callback:
                progress_callback(f"扫描失败: {e}", 0)
            return False

    def _sync_genres_from_beets(self):
        try:
            if not os.path.exists(BEETS_DB_PATH):
                logger.warning(f"Beets DB not found: {BEETS_DB_PATH}")
                return

            import sqlite3
            conn = sqlite3.connect(BEETS_DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT genres, path FROM items")
            rows = cur.fetchall()
            conn.close()

            count = 0
            for genre, path_blob in rows:
                if not path_blob:
                    continue
                path = path_blob.decode("utf-8", errors="replace") if isinstance(path_blob, bytes) else str(path_blob)
                if not path:
                    continue
                if genre and genre != "Unknown":
                    self._music_library.set_genre(path, genre, "beets")
                    count += 1
                elif not genre or genre == "Unknown":
                    self._music_library.set_genre(path, "Unclassified", "beets")
                    count += 1

            logger.info(f"Synced {count} genres from Beets (DB direct)")

        except Exception as e:
            logger.error(f"Sync genres error: {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "installed": self.is_installed(),
            "config_exists": os.path.exists(BEETS_CONFIG_PATH),
            "db_exists": os.path.exists(BEETS_DB_PATH),
        }
