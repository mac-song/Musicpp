import logging
import os
import sys
import glob
import time
from datetime import datetime

from .constants import CONFIG_DIR

LOG_DIR = os.path.join(CONFIG_DIR, "logs")

LOG_CATEGORIES = [
    ("all", "全部"),
    ("bass_engine", "音频引擎"),
    ("decoder_plugin_manager", "解码器插件"),
    ("media_extractor", "媒体提取"),
    ("study_manager", "学习管理"),
    ("study_window", "学习窗口"),
    ("main_window", "主窗口"),
    ("audio_service", "音频服务"),
    ("playback_manager", "播放管理"),
    ("theme_engine", "主题引擎"),
    ("subtitle_parser", "字幕解析"),
    ("config_manager", "配置管理"),
    ("lyric_manager", "歌词管理"),
    ("webdav_client", "WebDAV"),
    ("network", "网络"),
]


def setup_logger(name: str = "musicpp", level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(
        LOG_DIR,
        f"musicpp_{datetime.now().strftime('%Y%m%d')}.log"
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_log_files() -> list:
    os.makedirs(LOG_DIR, exist_ok=True)
    pattern = os.path.join(LOG_DIR, "musicpp_*.log")
    files = glob.glob(pattern)
    result = []
    for f in files:
        try:
            stat = os.stat(f)
            basename = os.path.basename(f)
            date_str = basename.replace("musicpp_", "").replace(".log", "")
            date_val = ""
            if len(date_str) == 8 and date_str.isdigit():
                date_val = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            result.append({
                "path": f,
                "name": basename,
                "date": date_val,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
        except OSError:
            continue
    result.sort(key=lambda x: x["mtime"], reverse=True)
    return result


def search_logs(keyword: str = "", category: str = "all", level_filter: str = "all",
                date_from: str = "", date_to: str = "", max_lines: int = 500) -> list:
    files = get_log_files()
    if date_from:
        files = [f for f in files if f["date"] >= date_from]
    if date_to:
        files = [f for f in files if f["date"] <= date_to]

    results = []
    level_order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_level = level_order.get(level_filter, 0)

    for f in files:
        try:
            with open(f["path"], "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if len(results) >= max_lines:
                        return results

                    if min_level > 0:
                        line_level = "DEBUG"
                        for lvl in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
                            if f"[{lvl}]" in line:
                                line_level = lvl
                                break
                        if level_order.get(line_level, 0) < min_level:
                            continue
                    else:
                        line_level = "DEBUG"
                        for lvl in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
                            if f"[{lvl}]" in line:
                                line_level = lvl
                                break

                    if category != "all":
                        cat_prefix = f" {category} -"
                        if cat_prefix not in line:
                            continue

                    if keyword and keyword.lower() not in line.lower():
                        continue

                    results.append({
                        "file": f["name"],
                        "date": f["date"],
                        "line": line.rstrip(),
                        "level": line_level,
                    })
        except OSError:
            continue

    return results


def delete_log_file(path: str) -> bool:
    try:
        if os.path.isfile(path) and os.path.dirname(path) == LOG_DIR:
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def cleanup_old_logs(months: int = 3) -> int:
    if months <= 0:
        return 0
    cutoff = time.time() - months * 30 * 24 * 3600
    files = get_log_files()
    deleted = 0
    for f in files:
        if f["mtime"] < cutoff:
            try:
                os.remove(f["path"])
                deleted += 1
            except OSError:
                continue
    return deleted


def get_total_log_size() -> int:
    files = get_log_files()
    return sum(f["size"] for f in files)


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


_msg_logger = setup_logger("musicpp.msgbox")


def log_msgbox(level: str, title: str, message: str):
    import traceback
    caller = traceback.extract_stack(limit=3)[0]
    source = f"{os.path.basename(caller.filename)}:{caller.lineno}"
    _msg_logger.info(f"[MsgBox:{level}] title=\"{title}\" msg=\"{message}\" src={source}")
