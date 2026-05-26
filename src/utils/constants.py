import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BASE_DIR)

CONFIG_DIR = os.path.join(ROOT_DIR, "config")
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")
BASS_PLUGINS_DIR = os.path.join(ROOT_DIR, "bass_plugins")


DB_PATH = os.path.join(CONFIG_DIR, "musicpp.db")
CONFIG_PATH = os.path.join(CONFIG_DIR, "musicpp.ini")
DECODER_REGISTRY_PATH = os.path.join(CONFIG_DIR, "decoder_plugins.json")

DEFAULT_WINDOW_WIDTH = 800
DEFAULT_WINDOW_HEIGHT = 600


CORE_AUDIO_FORMATS = [".mp3", ".wav", ".ogg", ".m4a", ".aac"]

EXTENDED_AUDIO_FORMATS = [
    ".flac", ".ape", ".mac", ".wma", ".wmv",
    ".alac", ".opus", ".mpc", ".mpp", ".spx",
    ".tta", ".wv", ".mid", ".midi", ".ac3",
    ".aiff", ".aif", ".dsf", ".dff", ".dts",
    ".tak", ".cda", ".voc", ".s3m", ".it",
    ".xm", ".mod", ".mtm", ".umx",
]

PLAYLIST_FORMATS = [".m3u", ".m3u8"]

SUPPORTED_AUDIO_FORMATS = CORE_AUDIO_FORMATS + EXTENDED_AUDIO_FORMATS

BASS_PLUGIN_REGISTRY = {
    "bass_aac": {
        "dll": "bass_aac.dll",
        "formats": [".aac", ".m4a", ".mp4"],
        "name": "AAC Decoder",
        "description": "支持AAC/M4A/MP4音频格式",
        "is_builtin": True,
        "is_official": False,
        "download_url": "https://www.un4seen.com/files/z/2/bass_aac24.zip",
    },
    "bass_flac": {
        "dll": "bassflac.dll",
        "formats": [".flac"],
        "name": "FLAC Decoder",
        "description": "支持FLAC无损音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/bassflac24.zip",
    },
    "bass_ape": {
        "dll": "bass_ape.dll",
        "formats": [".ape", ".mac"],
        "name": "APE Decoder",
        "description": "支持APE/MAC无损音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/bassape24.zip",
    },
    "bass_wma": {
        "dll": "basswma.dll",
        "formats": [".wma", ".wmv"],
        "name": "WMA Decoder",
        "description": "支持WMA/WMV音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/basswm24.zip",
    },
    "bass_alac": {
        "dll": "bass_alac.dll",
        "formats": [".alac"],
        "name": "ALAC Decoder",
        "description": "支持ALAC苹果无损音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/bassalac24.zip",
    },
    "bass_opus": {
        "dll": "bassopus.dll",
        "formats": [".opus"],
        "name": "OPUS Decoder",
        "description": "支持OPUS音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/bassopus24.zip",
    },
    "bass_mpc": {
        "dll": "bass_mpc.dll",
        "formats": [".mpc", ".mpp"],
        "name": "MPC Decoder",
        "description": "支持Musepack音频格式",
        "is_builtin": False,
        "is_official": False,
        "download_url": "https://www.un4seen.com/files/z/2/bass_mpc24.zip",
    },
    "bass_spx": {
        "dll": "bass_spx.dll",
        "formats": [".spx"],
        "name": "Speex Decoder",
        "description": "支持Speex音频格式",
        "is_builtin": False,
        "is_official": False,
        "download_url": "https://www.un4seen.com/files/z/2/bass_spx24.zip",
    },
    "bass_tta": {
        "dll": "bass_tta.dll",
        "formats": [".tta"],
        "name": "TTA Decoder",
        "description": "支持TTA无损音频格式",
        "is_builtin": False,
        "is_official": False,
        "download_url": "https://www.un4seen.com/files/z/2/bass_tta24.zip",
    },
    "basswv": {
        "dll": "basswv.dll",
        "formats": [".wv"],
        "name": "WavPack Decoder",
        "description": "支持WavPack音频格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/basswv24.zip",
    },
    "bassmidi": {
        "dll": "bassmidi.dll",
        "formats": [".mid", ".midi"],
        "name": "MIDI Decoder",
        "description": "支持MIDI音乐格式",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/bassmidi24.zip",
    },
    "bass_ac3": {
        "dll": "bass_ac3.dll",
        "formats": [".ac3"],
        "name": "AC3 Decoder",
        "description": "支持AC3杜比音频格式",
        "is_builtin": False,
        "is_official": False,
        "download_url": "https://www.un4seen.com/files/z/2/bass_ac324.zip",
    },
    "basshls": {
        "dll": "basshls.dll",
        "formats": [".m3u8"],
        "name": "HLS Decoder",
        "description": "支持HLS流媒体播放（M3U8）",
        "is_builtin": False,
        "is_official": True,
        "download_url": "https://www.un4seen.com/files/basshls24.zip",
    },
}

LYRIC_SOURCES = [
    "local", "lrclib", "netease", "gequbao"
]

DEFAULT_LYRIC_SOURCES = ["local", "lrclib", "netease", "gequbao"]



EVENT_PLAYBACK_STATE_CHANGED = "playback_state_changed"
EVENT_TRACK_CHANGED = "track_changed"
EVENT_LYRIC_LOADED = "lyric_loaded"
EVENT_LYRIC_GENERATED = "lyric_generated"
EVENT_DOWNLOAD_PROGRESS = "download_progress"
EVENT_PLUGIN_STATUS_CHANGED = "plugin_status_changed"
EVENT_CONFIG_UPDATED = "config_updated"
EVENT_PLAY_FAILED = "play_failed"

PLAYBACK_STOPPED = 0
PLAYBACK_PLAYING = 1
PLAYBACK_PAUSED = 2

PLAY_MODE_SEQUENCE = 0
PLAY_MODE_LOOP_ALL = 1
PLAY_MODE_LOOP_SINGLE = 2
PLAY_MODE_RANDOM = 3
