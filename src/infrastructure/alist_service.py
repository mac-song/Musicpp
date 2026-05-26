import os
import subprocess
import sys
import time
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class AListService:
    _instance: Optional["AListService"] = None
    _process: Optional[subprocess.Popen] = None
    _port: int = 5244
    _data_dir: str = ""
    _binary_path: str = ""

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_binary_path(cls) -> str:
        if cls._binary_path:
            return cls._binary_path
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [
            os.path.join(base, "alist.exe"),
            os.path.join(base, "alist"),
            os.path.join(base, "tools", "alist.exe"),
            os.path.join(base, "tools", "alist"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                cls._binary_path = p
                return p
        return ""

    @classmethod
    def is_available(cls) -> bool:
        return bool(cls.get_binary_path())

    @classmethod
    def get_data_dir(cls) -> str:
        if cls._data_dir:
            return cls._data_dir
        if getattr(sys, "frozen", False):
            base = os.path.join(os.path.dirname(sys.executable), "alist_data")
        else:
            base = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "alist_data",
            )
        os.makedirs(base, exist_ok=True)
        cls._data_dir = base
        return base

    @classmethod
    def start(cls, port: int = 5244) -> bool:
        if cls._process is not None and cls._process.poll() is None:
            logger.debug("AList already running")
            return True

        binary = cls.get_binary_path()
        if not binary:
            logger.info("AList binary not found, skipping auto-start")
            return False

        cls._port = port
        data_dir = cls.get_data_dir()

        env = os.environ.copy()
        env["ALIST_DATA"] = data_dir
        env["ALIST_PORT"] = str(port)
        env["ALIST_NO_LOG"] = "true"

        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.CREATE_NO_WINDOW

            cls._process = subprocess.Popen(
                [binary, "server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            logger.info(f"AList started on port {port} (PID: {cls._process.pid})")
            return True
        except Exception as e:
            logger.warning(f"Failed to start AList: {e}")
            cls._process = None
            return False

    @classmethod
    def stop(cls):
        if cls._process is None:
            return
        try:
            if cls._process.poll() is None:
                cls._process.terminate()
                try:
                    cls._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls._process.kill()
                    cls._process.wait(timeout=3)
                logger.info("AList stopped")
        except Exception as e:
            logger.warning(f"Error stopping AList: {e}")
        finally:
            cls._process = None

    @classmethod
    def is_running(cls) -> bool:
        return cls._process is not None and cls._process.poll() is None

    @classmethod
    def get_port(cls) -> int:
        return cls._port

    @classmethod
    def get_server_url(cls) -> str:
        return f"http://localhost:{cls._port}"

    @classmethod
    def get_webdav_url(cls) -> str:
        return f"http://localhost:{cls._port}/dav/"

    @classmethod
    def wait_ready(cls, timeout: float = 15.0) -> bool:
        if not cls.is_running():
            return False
        import urllib.request
        import urllib.error

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"http://localhost:{cls._port}/api/public/settings")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        logger.info("AList is ready")
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("AList did not become ready in time")
        return False

    @classmethod
    def set_admin_password(cls, password: str = "admin") -> bool:
        binary = cls.get_binary_path()
        if not binary:
            return False
        data_dir = cls.get_data_dir()
        env = os.environ.copy()
        env["ALIST_DATA"] = data_dir

        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [binary, "admin", "set", password],
                capture_output=True,
                text=True,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("AList admin password set")
                return True
            logger.warning(f"AList set password failed: {result.stderr}")
            return False
        except Exception as e:
            logger.warning(f"Failed to set AList password: {e}")
            return False

    @classmethod
    def get_admin_password(cls) -> Optional[str]:
        binary = cls.get_binary_path()
        if not binary:
            return None
        data_dir = cls.get_data_dir()
        env = os.environ.copy()
        env["ALIST_DATA"] = data_dir

        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [binary, "admin", "random"],
                capture_output=True,
                text=True,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=10,
            )
            output = (result.stdout + result.stderr).strip()
            for line in output.splitlines():
                if "password" in line.lower():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return parts[-1].strip()
            return None
        except Exception:
            return None
