import os
import sys
import threading
from ctypes import (
    CDLL, CFUNCTYPE, POINTER, byref, c_bool, c_double, c_uint32, c_float,
    c_int, c_ulong, c_ulonglong, c_void_p, c_wchar_p, c_char_p, cdll
)

c_dword = c_uint32
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlparse

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class _ProxyHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.target_url = server.target_url
        self.target_headers = server.target_headers
        super().__init__(request, client_address, server)

    def do_GET(self):
        import urllib.request
        try:
            headers = dict(self.target_headers or {})
            range_header = self.headers.get("Range")
            if range_header:
                headers["Range"] = range_header

            req = urllib.request.Request(
                self.target_url,
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                skip_headers = {"transfer-encoding", "connection", "accept-ranges"}
                for key, val in resp.getheaders():
                    if key.lower() not in skip_headers:
                        self.send_header(key, val)
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                try:
                    while True:
                        chunk = resp.read(32768)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        except Exception as e:
            try:
                self.send_error(502, str(e))
            except Exception:
                pass

    def do_HEAD(self):
        import urllib.request
        try:
            headers = dict(self.target_headers or {})
            req = urllib.request.Request(
                self.target_url,
                headers=headers,
                method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, val)
                self.end_headers()
        except Exception as e:
            try:
                self.send_error(502, str(e))
            except Exception:
                pass

    def log_message(self, format, *args):
        pass


class BASSEngine:
    BASS_DEVICE_ENABLED = 1
    BASS_DEVICE_DEFAULT = 2

    BASS_POS_BYTE = 0
    BASS_POS_MUSIC_ORDER = 1
    BASS_POS_OGG = 3
    BASS_POS_INEXACT = 0x8000000
    BASS_POS_DECODE = 0x10000000
    BASS_POS_DECODETO = 0x20000000

    BASS_ACTIVE_STOPPED = 0
    BASS_ACTIVE_PLAYING = 1
    BASS_ACTIVE_STALLED = 2
    BASS_ACTIVE_PAUSED = 3

    BASS_SAMPLE_LOOP = 4
    BASS_STREAM_AUTOFREE = 0x40000
    BASS_STREAM_DECODE = 0x200000
    BASS_UNICODE = 0x80000000

    BASS_ATTRIB_VOL = 2
    BASS_ATTRIB_PAN = 3
    BASS_ATTRIB_FREQ = 1

    BASS_DATA_FFT256 = 0x80000000
    BASS_DATA_FFT512 = 0x80000001
    BASS_DATA_FFT1024 = 0x80000002
    BASS_DATA_FFT2048 = 0x80000003
    BASS_DATA_FFT4096 = 0x80000004
    BASS_DATA_FFT8192 = 0x80000005
    BASS_DATA_FFT16384 = 0x80000006
    BASS_DATA_FFT32768 = 0x80000007

    BASS_SYNC_END = 2
    BASS_SYNC_POS = 3

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
        self._bass = None
        self._bass_aac = None
        self._current_stream = 0
        self._volume = 1.0
        self._initialized_flag = False
        self._sync_callbacks = []
        self._proxy_server = None
        self._proxy_port = 0
        self._proxy_thread = None
        self._initialized = True

    def _find_bass_dll(self):
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "bass.dll"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "bass.dll"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bass.dll"),
            "bass.dll",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        return None

    def _find_bass_aac_dll(self):
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "bass_aac.dll"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "bass_aac.dll"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bass_aac.dll"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        return None

    def _start_proxy(self):
        for port in range(51900, 51999):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), _ProxyHandler)
                server.target_url = None
                server.target_headers = None
                self._proxy_server = server
                self._proxy_port = port
                self._proxy_thread = threading.Thread(
                    target=server.serve_forever, daemon=True
                )
                self._proxy_thread.start()
                logger.info(f"BASS proxy server started on port {port}")
                return
            except OSError:
                continue
        logger.warning("Failed to start BASS proxy server")

    def initialize(self, device: int = -1, freq: int = 44100, flags: int = 0) -> bool:
        try:
            bass_dll_path = self._find_bass_dll()
            if bass_dll_path:
                bass_dir = os.path.dirname(bass_dll_path)
                if bass_dir and bass_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = bass_dir + os.pathsep + os.environ.get("PATH", "")
                self._bass = cdll.LoadLibrary(bass_dll_path)
            else:
                self._bass = cdll.LoadLibrary("bass.dll")

            self._setup_function_prototypes()

            result = self._bass.BASS_Init(device, freq, flags, None, None)
            if result:
                self._initialized_flag = True
                version = self._bass.BASS_GetVersion()
                logger.info(f"BASS initialized successfully, version: {version}")

                self._load_plugins()
                self._start_proxy()

                return True
            else:
                error_code = self._bass.BASS_ErrorGetCode()
                logger.error(f"BASS_Init failed with error code: {error_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize BASS: {e}")
            return False

    def _load_plugins(self):
        try:
            self._bass.BASS_PluginLoad.restype = c_ulong
            self._bass.BASS_PluginLoad.argtypes = [c_char_p, c_ulong]
        except Exception:
            pass
        from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
        dpm = DecoderPluginManager()
        dpm.set_bass_engine(self)
        dpm.scan_and_load()

    def load_bass_plugin(self, dll_path: str):
        try:
            self._bass.BASS_PluginLoad.restype = c_ulong
            self._bass.BASS_PluginLoad.argtypes = [c_char_p, c_ulong]
            handle = self._bass.BASS_PluginLoad(dll_path.encode("utf-8"), 0)
            if handle:
                return handle
            error_code = self._bass.BASS_ErrorGetCode()
            logger.debug(f"BASS_PluginLoad failed for {dll_path}, error: {error_code}")
            return 0
        except Exception as e:
            logger.warning(f"Exception loading BASS plugin {dll_path}: {e}")
            return 0

    def _setup_function_prototypes(self):
        self._bass.BASS_Init.restype = c_bool
        self._bass.BASS_Init.argtypes = [c_int, c_dword, c_dword, c_void_p, c_void_p]

        self._bass.BASS_Free.restype = c_bool
        self._bass.BASS_Free.argtypes = []

        self._bass.BASS_StreamCreateFile.restype = c_ulong
        self._bass.BASS_StreamCreateFile.argtypes = [c_bool, c_void_p, c_ulonglong, c_ulonglong, c_ulong]

        self._bass.BASS_StreamFree.restype = c_bool
        self._bass.BASS_StreamFree.argtypes = [c_ulong]

        self._bass.BASS_StreamCreateURL.restype = c_ulong
        self._bass.BASS_StreamCreateURL.argtypes = [c_char_p, c_ulong, c_ulong, c_void_p, c_void_p]

        self._bass.BASS_ChannelPlay.restype = c_bool
        self._bass.BASS_ChannelPlay.argtypes = [c_ulong, c_bool]

        self._bass.BASS_ChannelPause.restype = c_bool
        self._bass.BASS_ChannelPause.argtypes = [c_ulong]

        self._bass.BASS_ChannelStop.restype = c_bool
        self._bass.BASS_ChannelStop.argtypes = [c_ulong]

        self._bass.BASS_ChannelIsActive.restype = c_dword
        self._bass.BASS_ChannelIsActive.argtypes = [c_ulong]

        self._bass.BASS_ChannelGetPosition.restype = c_ulonglong
        self._bass.BASS_ChannelGetPosition.argtypes = [c_ulong, c_dword]

        self._bass.BASS_ChannelSetPosition.restype = c_bool
        self._bass.BASS_ChannelSetPosition.argtypes = [c_ulong, c_ulonglong, c_dword]

        self._bass.BASS_ChannelGetLength.restype = c_ulonglong
        self._bass.BASS_ChannelGetLength.argtypes = [c_ulong, c_dword]

        self._bass.BASS_ChannelBytes2Seconds.restype = c_double
        self._bass.BASS_ChannelBytes2Seconds.argtypes = [c_ulong, c_ulonglong]

        self._bass.BASS_ChannelSeconds2Bytes.restype = c_ulonglong
        self._bass.BASS_ChannelSeconds2Bytes.argtypes = [c_ulong, c_double]

        self._bass.BASS_ChannelSetAttribute.restype = c_bool
        self._bass.BASS_ChannelSetAttribute.argtypes = [c_ulong, c_dword, c_float]

        self._bass.BASS_ChannelGetAttribute.restype = c_bool
        self._bass.BASS_ChannelGetAttribute.argtypes = [c_ulong, c_dword, POINTER(c_float)]

        self._bass.BASS_ChannelSlideAttribute.restype = c_bool
        self._bass.BASS_ChannelSlideAttribute.argtypes = [c_ulong, c_dword, c_float, c_dword]

        self._bass.BASS_ChannelGetData.restype = c_dword
        self._bass.BASS_ChannelGetData.argtypes = [c_ulong, c_void_p, c_dword]

        self._bass.BASS_ChannelSetSync.restype = c_ulong
        self._bass.BASS_ChannelSetSync.argtypes = [c_ulong, c_dword, c_ulonglong, c_void_p, c_void_p]

        self._bass.BASS_ChannelRemoveSync.restype = c_bool
        self._bass.BASS_ChannelRemoveSync.argtypes = [c_ulong, c_ulong]

        self._bass.BASS_GetVersion.restype = c_dword
        self._bass.BASS_GetVersion.argtypes = []

        self._bass.BASS_ErrorGetCode.restype = c_int
        self._bass.BASS_ErrorGetCode.argtypes = []

    def load(self, file_path: str) -> bool:
        if not self._initialized_flag:
            logger.error("BASS not initialized")
            return False

        self.unload()

        try:
            file_path = os.path.normpath(file_path)
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return False

            wchar_path = c_wchar_p(file_path)
            self._current_stream = self._bass.BASS_StreamCreateFile(
                False, wchar_path, 0, 0,
                self.BASS_STREAM_AUTOFREE | self.BASS_UNICODE
            )

            if self._current_stream == 0:
                error_code = self._bass.BASS_ErrorGetCode()
                logger.error(f"Failed to load file: {file_path}, error: {error_code}")
                return False

            self.set_volume(self._volume)
            logger.info(f"Loaded audio file: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error loading file {file_path}: {e}")
            return False

    def load_url(self, url: str, headers: dict = None) -> bool:
        if not self._initialized_flag:
            logger.error("BASS not initialized")
            return False

        self.unload()

        try:
            if headers and self._proxy_server:
                self._proxy_server.target_url = url
                self._proxy_server.target_headers = headers
                proxy_url = f"http://127.0.0.1:{self._proxy_port}/stream"
                url_bytes = proxy_url.encode("utf-8")
            else:
                url_bytes = url.encode("utf-8")

            flags = self.BASS_STREAM_AUTOFREE

            self._current_stream = self._bass.BASS_StreamCreateURL(
                url_bytes, 0, flags, None, None
            )

            if self._current_stream == 0:
                error_code = self._bass.BASS_ErrorGetCode()
                logger.error(f"Failed to load URL: {url}, error: {error_code}")
                return False

            self.set_volume(self._volume)
            logger.info(f"Loaded URL stream: {url[:80]}...")
            return True

        except Exception as e:
            logger.error(f"Error loading URL {url}: {e}")
            return False

    def play(self) -> bool:
        if self._current_stream == 0:
            return False
        try:
            result = self._bass.BASS_ChannelPlay(self._current_stream, False)
            return result
        except Exception as e:
            logger.error(f"BASS play error: {e}")
            return False

    def pause(self) -> bool:
        if self._current_stream == 0:
            return False
        try:
            result = self._bass.BASS_ChannelPause(self._current_stream)
            return result
        except Exception as e:
            logger.error(f"BASS pause error: {e}")
            return False

    def stop(self) -> bool:
        if self._current_stream == 0:
            return False
        try:
            result = self._bass.BASS_ChannelStop(self._current_stream)
            return result
        except Exception as e:
            logger.error(f"BASS stop error: {e}")
            return False

    def unload(self) -> None:
        if self._current_stream != 0:
            try:
                self._bass.BASS_StreamFree(self._current_stream)
            except Exception as e:
                logger.error(f"BASS unload error: {e}")
            self._current_stream = 0
        self._orig_freq = 0

    def seek(self, position: float) -> bool:
        if self._current_stream == 0:
            return False
        try:
            pos_bytes = self._bass.BASS_ChannelSeconds2Bytes(self._current_stream, position)
            result = self._bass.BASS_ChannelSetPosition(
                self._current_stream, pos_bytes, self.BASS_POS_BYTE
            )
            return result
        except Exception as e:
            logger.error(f"BASS seek error: {e}")
            return False

    def get_position(self) -> float:
        if self._current_stream == 0:
            return 0.0
        try:
            pos_bytes = self._bass.BASS_ChannelGetPosition(self._current_stream, self.BASS_POS_BYTE)
            return self._bass.BASS_ChannelBytes2Seconds(self._current_stream, pos_bytes)
        except Exception as e:
            logger.error(f"BASS get_position error: {e}")
            return 0.0

    def get_duration(self) -> float:
        if self._current_stream == 0:
            return 0.0
        try:
            len_bytes = self._bass.BASS_ChannelGetLength(self._current_stream, self.BASS_POS_BYTE)
            return self._bass.BASS_ChannelBytes2Seconds(self._current_stream, len_bytes)
        except Exception as e:
            logger.error(f"BASS get_duration error: {e}")
            return 0.0

    def set_volume(self, volume: float) -> bool:
        self._volume = max(0.0, min(1.0, volume))
        if self._current_stream == 0:
            return False
        try:
            result = self._bass.BASS_ChannelSetAttribute(
                self._current_stream, self.BASS_ATTRIB_VOL, self._volume
            )
            return result
        except Exception as e:
            logger.error(f"BASS set_volume error: {e}")
            return False

    def set_speed(self, rate: float) -> bool:
        if self._current_stream == 0:
            return False
        try:
            if not hasattr(self, '_orig_freq') or self._orig_freq <= 0:
                freq = c_float()
                self._bass.BASS_ChannelGetAttribute(
                    self._current_stream, self.BASS_ATTRIB_FREQ, byref(freq)
                )
                self._orig_freq = freq.value if freq.value > 0 else 44100.0
            new_freq = self._orig_freq * rate
            result = self._bass.BASS_ChannelSetAttribute(
                self._current_stream, self.BASS_ATTRIB_FREQ, c_float(new_freq)
            )
            return result
        except Exception as e:
            logger.error(f"BASS set_speed error: {e}")
            return False

    def get_volume(self) -> float:
        if self._current_stream == 0:
            return self._volume
        try:
            vol = c_float()
            self._bass.BASS_ChannelGetAttribute(self._current_stream, self.BASS_ATTRIB_VOL, byref(vol))
            return vol.value
        except Exception as e:
            logger.error(f"BASS get_volume error: {e}")
            return self._volume

    def fade_out(self, duration_ms: int = 100) -> bool:
        if self._current_stream == 0:
            return False
        try:
            return self._bass.BASS_ChannelSlideAttribute(
                self._current_stream, self.BASS_ATTRIB_VOL, 0.0, duration_ms
            )
        except Exception as e:
            logger.error(f"BASS fade_out error: {e}")
            return False

    def fade_in(self, duration_ms: int = 100) -> bool:
        if self._current_stream == 0:
            return False
        try:
            return self._bass.BASS_ChannelSlideAttribute(
                self._current_stream, self.BASS_ATTRIB_VOL, self._volume, duration_ms
            )
        except Exception as e:
            logger.error(f"BASS fade_in error: {e}")
            return False

    def get_playback_state(self) -> int:
        if self._current_stream == 0:
            return self.BASS_ACTIVE_STOPPED
        try:
            return self._bass.BASS_ChannelIsActive(self._current_stream)
        except Exception as e:
            logger.error(f"BASS get_playback_state error: {e}")
            return self.BASS_ACTIVE_STOPPED

    def is_playing(self) -> bool:
        return self.get_playback_state() == self.BASS_ACTIVE_PLAYING

    def is_paused(self) -> bool:
        return self.get_playback_state() == self.BASS_ACTIVE_PAUSED

    def is_stopped(self) -> bool:
        return self.get_playback_state() == self.BASS_ACTIVE_STOPPED

    def has_stream(self) -> bool:
        return self._current_stream != 0

    def load_decode(self, file_path: str) -> int:
        if not self._initialized_flag:
            return 0
        try:
            file_path = os.path.normpath(file_path)
            if not os.path.exists(file_path):
                return 0
            wchar_path = c_wchar_p(file_path)
            stream = self._bass.BASS_StreamCreateFile(
                False, wchar_path, 0, 0,
                self.BASS_STREAM_DECODE | self.BASS_UNICODE
            )
            if stream == 0:
                error_code = self._bass.BASS_ErrorGetCode()
                logger.error(f"load_decode failed for: {file_path}, BASS error: {error_code}")
            return stream
        except Exception as e:
            logger.error(f"load_decode exception: {e}")
            return 0

    def free_stream(self, stream: int) -> None:
        if stream and stream != 0:
            try:
                self._bass.BASS_StreamFree(stream)
            except Exception as e:
                logger.error(f"BASS free_stream error: {e}")

    def cleanup(self) -> None:
        if self._current_stream != 0:
            try:
                self._bass.BASS_ChannelStop(self._current_stream)
                self._bass.BASS_StreamFree(self._current_stream)
            except Exception:
                pass
            self._current_stream = 0

        if self._proxy_server:
            try:
                self._proxy_server.shutdown()
            except Exception:
                pass
            self._proxy_server = None

        if self._initialized_flag and self._bass:
            try:
                self._bass.BASS_Free()
            except Exception:
                pass
            self._initialized_flag = False


