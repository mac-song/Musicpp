import os
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

from src.infrastructure.subtitle_parser import SubtitleLine
from src.plugins.transcription_interface import TranscriptionInterface
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

WHISPER_MODELS = [
    {"name": "tiny", "params": "39M", "vram": "~150MB", "speed": "极快", "desc": "快速预览，精度一般"},
    {"name": "tiny.en", "params": "39M", "vram": "~150MB", "speed": "极快", "desc": "英文专用"},
    {"name": "base", "params": "74M", "vram": "~250MB", "speed": "很快", "desc": "推荐默认，精度与速度平衡"},
    {"name": "base.en", "params": "74M", "vram": "~250MB", "speed": "很快", "desc": "英文专用"},
    {"name": "small", "params": "244M", "vram": "~600MB", "speed": "中等", "desc": "精度较好"},
    {"name": "small.en", "params": "244M", "vram": "~600MB", "speed": "中等", "desc": "英文专用"},
    {"name": "medium", "params": "769M", "vram": "~1.5GB", "speed": "较慢", "desc": "高精度，需2GB+内存"},
    {"name": "large-v3", "params": "1550M", "vram": "~3GB", "speed": "慢", "desc": "最高精度，需4GB+内存"},
]

PIP_MIRRORS = [
    {"name": "默认源 (PyPI)", "url": ""},
    {"name": "清华大学", "url": "https://pypi.tuna.tsinghua.edu.cn/simple"},
    {"name": "阿里云", "url": "https://mirrors.aliyun.com/pypi/simple/"},
    {"name": "中国科技大学", "url": "https://pypi.mirrors.ustc.edu.cn/simple/"},
    {"name": "豆瓣", "url": "https://pypi.douban.com/simple/"},
    {"name": "腾讯云", "url": "https://mirrors.cloud.tencent.com/pypi/simple/"},
]

HF_MIRRORS = [
    {"name": "默认 (huggingface.co)", "url": ""},
    {"name": "hf-mirror.com", "url": "https://hf-mirror.com"},
]


class WhisperPlugin(TranscriptionInterface):
    meta = {
        "id": "whisper",
        "name": "Whisper 语音识别",
        "version": "1.0.0",
        "author": "Music++",
        "description": "基于 faster-whisper 的语音转字幕插件，支持多种模型和语言",
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._model = None
        self._current_model_name = None

    def is_available(self) -> bool:
        try:
            import faster_whisper
            return True
        except ImportError:
            return False

    def get_status(self) -> Dict[str, Any]:
        status = {
            "installed": False,
            "version": "",
            "device": "CPU",
            "cuda_available": False,
            "model_loaded": self._model is not None,
            "current_model": self._current_model_name or "",
        }

        try:
            import faster_whisper
            status["installed"] = True
            status["version"] = getattr(faster_whisper, "__version__", "unknown")
        except ImportError:
            return status

        try:
            import torch
            status["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                status["device"] = "CUDA"
        except ImportError:
            pass

        return status

    def get_models(self) -> List[Dict[str, Any]]:
        return list(WHISPER_MODELS)

    @staticmethod
    def _apply_hf_mirror(hf_mirror_url: str = ""):
        if hf_mirror_url:
            os.environ["HF_ENDPOINT"] = hf_mirror_url
            try:
                import huggingface_hub.constants
                huggingface_hub.constants.ENDPOINT = hf_mirror_url
                if hasattr(huggingface_hub.constants, "HUGGINGFACE_CO_URL_TEMPLATE"):
                    huggingface_hub.constants.HUGGINGFACE_CO_URL_TEMPLATE = (
                        hf_mirror_url.rstrip("/") + "/{repo_id}/resolve/{revision}/{filename}"
                    )
                if hasattr(huggingface_hub.constants, "HUGGINGFACE_CO_URL_HOME"):
                    huggingface_hub.constants.HUGGINGFACE_CO_URL_HOME = (
                        hf_mirror_url.rstrip("/") + "/"
                    )
            except Exception:
                pass
            logger.info(f"Using HuggingFace mirror: {hf_mirror_url}")
        else:
            os.environ.pop("HF_ENDPOINT", None)
            try:
                import huggingface_hub.constants
                huggingface_hub.constants.ENDPOINT = huggingface_hub.constants._HF_DEFAULT_ENDPOINT
                if hasattr(huggingface_hub.constants, "HUGGINGFACE_CO_URL_TEMPLATE"):
                    huggingface_hub.constants.HUGGINGFACE_CO_URL_TEMPLATE = (
                        "https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"
                    )
                if hasattr(huggingface_hub.constants, "HUGGINGFACE_CO_URL_HOME"):
                    huggingface_hub.constants.HUGGINGFACE_CO_URL_HOME = (
                        "https://huggingface.co/"
                    )
            except Exception:
                pass

    def install(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        mirror_url: str = "",
    ) -> bool:
        try:
            if progress_callback:
                progress_callback("准备安装 faster-whisper...", 5)

            logger.info(f"Installing faster-whisper (mirror={mirror_url or 'default'})...")

            cmd = [sys.executable, "-m", "pip", "install", "faster-whisper", "--progress-bar", "off"]
            if mirror_url:
                cmd += ["-i", mirror_url, "--trusted-host", mirror_url.split("//")[-1].split("/")[0]]

            if progress_callback:
                progress_callback("正在下载安装 faster-whisper...", 10)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            output_lines = []
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    logger.info(f"[pip] {line}")
                    clean = line.strip()
                    if clean.startswith("Collecting"):
                        pkg = clean[len("Collecting"):].strip()
                        if progress_callback:
                            progress_callback(f"收集依赖: {pkg}", 20)
                    elif clean.startswith("Downloading"):
                        if progress_callback:
                            progress_callback(f"下载中: {clean[len('Downloading'):].strip()}", 35)
                    elif "Downloading" in clean:
                        if progress_callback:
                            progress_callback("下载依赖包...", 40)
                    elif clean.startswith("Installing collected"):
                        if progress_callback:
                            progress_callback("正在安装到 Python 环境...", 70)
                    elif clean.startswith("Successfully installed"):
                        if progress_callback:
                            progress_callback("安装完成!", 90)
                    elif "Requirement already satisfied" in clean:
                        if progress_callback:
                            progress_callback(f"已满足: {clean}", 30)
                    elif "error" in clean.lower() or "Error" in clean:
                        if progress_callback:
                            progress_callback(f"错误: {clean}", -1)

            proc.wait(timeout=600)

            if proc.returncode == 0:
                logger.info("faster-whisper installed successfully")
                if progress_callback:
                    progress_callback("安装成功!", 100)
                return True
            else:
                error_output = "\n".join(output_lines[-10:])
                logger.error(f"pip install failed (rc={proc.returncode}): {error_output}")
                if progress_callback:
                    progress_callback(f"安装失败 (退出码 {proc.returncode})", -1)
                return False

        except subprocess.TimeoutExpired:
            logger.error("pip install timed out")
            if progress_callback:
                progress_callback("安装超时（10分钟限制）", -1)
            return False
        except Exception as e:
            logger.error(f"Install error: {e}")
            if progress_callback:
                progress_callback(f"安装异常: {e}", -1)
            return False

    def uninstall(
        self,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> bool:
        try:
            self._model = None
            self._current_model_name = None

            if progress_callback:
                progress_callback("正在卸载 faster-whisper...", 10)

            cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "faster-whisper"]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            output_lines = []
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    logger.info(f"[pip uninstall] {line}")
                    clean = line.strip()
                    if "Successfully uninstalled" in clean:
                        if progress_callback:
                            progress_callback("卸载成功!", 90)
                    elif "Found existing installation" in clean:
                        if progress_callback:
                            progress_callback("找到已安装版本，正在卸载...", 30)

            proc.wait(timeout=120)

            if proc.returncode == 0:
                logger.info("faster-whisper uninstalled successfully")
                if progress_callback:
                    progress_callback("卸载完成!", 100)
                return True
            else:
                logger.error(f"pip uninstall failed: {proc.returncode}")
                if progress_callback:
                    progress_callback(f"卸载失败 (退出码 {proc.returncode})", -1)
                return False

        except Exception as e:
            logger.error(f"Uninstall error: {e}")
            if progress_callback:
                progress_callback(f"卸载异常: {e}", -1)
            return False

    def download_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        hf_mirror_url: str = "",
    ) -> bool:
        try:
            if progress_callback:
                progress_callback(f"正在加载模型 {model_name}...", 5)

            self._apply_hf_mirror(hf_mirror_url)

            if hf_mirror_url and progress_callback:
                progress_callback(f"使用 HuggingFace 镜像: {hf_mirror_url}", 10)

            from faster_whisper import WhisperModel

            logger.info(f"Downloading Whisper model: {model_name}")

            compute_type = "int8"
            device = "cpu"

            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float16"
            except ImportError:
                pass

            if progress_callback:
                progress_callback(f"正在下载/加载模型 {model_name}（设备: {device}）...", 20)

            model = WhisperModel(model_name, device=device, compute_type=compute_type)

            self._model = model
            self._current_model_name = model_name

            if progress_callback:
                progress_callback(f"模型 {model_name} 已就绪!", 100)

            logger.info(f"Whisper model '{model_name}' downloaded and loaded successfully (device={device}, compute_type={compute_type})")
            return True

        except Exception as e:
            logger.error(f"Download model error: {e}")
            logger.error(traceback.format_exc())
            if progress_callback:
                hint = "连接超时，请尝试切换 HuggingFace 镜像源后重试" if "ConnectTimeout" in str(e) or "10060" in str(e) else str(e)
                progress_callback(f"模型下载失败: {hint}", -1)
            return False

    def _ensure_model(self, model_name: str, device: str = "auto", compute_type: str = "auto", hf_mirror_url: str = "") -> bool:
        if self._model is not None and self._current_model_name == model_name:
            return True

        self._apply_hf_mirror(hf_mirror_url)

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error("faster-whisper not installed")
            return False

        actual_device = device
        if actual_device == "auto":
            actual_device = "cpu"
            try:
                import torch
                if torch.cuda.is_available():
                    actual_device = "cuda"
            except ImportError:
                pass

        actual_compute = compute_type
        if actual_compute == "auto":
            actual_compute = "float16" if actual_device == "cuda" else "int8"

        if self._model is not None:
            try:
                del self._model
            except Exception:
                pass
            self._model = None
            try:
                import gc
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
            except Exception:
                pass

        try:
            logger.info(f"Loading Whisper model: {model_name} (device={actual_device}, compute_type={actual_compute})")
            self._model = WhisperModel(model_name, device=actual_device, compute_type=actual_compute)
            self._current_model_name = model_name
            return True
        except Exception as e:
            logger.error(f"Load model error: {e}")
            self._model = None
            self._current_model_name = None
            return False

    def transcribe(
        self,
        audio_path: str,
        model_name: str = "base",
        language: str = None,
        device: str = "auto",
        compute_type: str = "auto",
        progress_callback: Optional[Callable[[int], None]] = None,
        hf_mirror_url: str = "",
    ) -> Optional[List[SubtitleLine]]:
        try:
            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found: {audio_path}")
                return None

            if progress_callback:
                progress_callback(5)

            if not self._ensure_model(model_name, device, compute_type, hf_mirror_url):
                logger.error("Failed to load Whisper model")
                return None

            if progress_callback:
                progress_callback(15)

            transcribe_kwargs = {
                "beam_size": 5,
                "vad_filter": True,
                "vad_parameters": {
                    "min_silence_duration_ms": 300,
                    "speech_pad_ms": 200,
                },
            }
            if language:
                transcribe_kwargs["language"] = language

            logger.info(f"Starting transcription: {os.path.basename(audio_path)}, model={model_name}, language={language or 'auto'}")

            segments_iter, info = self._model.transcribe(audio_path, **transcribe_kwargs)

            if progress_callback:
                progress_callback(20)

            subtitles = []
            idx = 0
            duration = getattr(info, "duration", 0)

            for seg in segments_iter:
                start_ms = int(seg.start * 1000)
                end_ms = int(seg.end * 1000)
                text = seg.text.strip()

                if not text:
                    continue

                subtitles.append(
                    SubtitleLine(
                        index=idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                    )
                )
                idx += 1

                if progress_callback and duration > 0 and idx % 5 == 0:
                    progress_pct = min(int(20 + (seg.end / duration) * 75), 95)
                    progress_callback(progress_pct)

            if progress_callback:
                progress_callback(100)

            logger.info(f"Transcription complete: {len(subtitles)} segments, language={getattr(info, 'language', 'unknown')}, duration={duration:.1f}s")
            return subtitles

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            logger.error(traceback.format_exc())
            return None
