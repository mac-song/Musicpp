<div align="center">

<img src="src/cover.gif" width="120" height="120" alt="Music++" />

# Music++

**A feature-rich desktop music player built with Python & PySide6**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4.svg)](https://www.microsoft.com/windows)

[English](#features) · [中文](#功能概览) · [Plugin Development](#plugin-development) · [Architecture](#architecture)

</div>

---

## Features

### 🎵 Music Playback
- **Local Music** — Browse and play local audio files with directory tree navigation
- **Online Music** — Stream music from online sources via extensible plugins (NetEase, Bilibili, etc.)
- **30+ Audio Formats** — MP3, WAV, FLAC, APE, OGG, M4A, AAC, WMA, OPUS, TAK, DSF, and more via BASS engine + decoder plugins
- **Playback Modes** — Sequential, Loop All, Loop Single, Random
- **A-B Repeat** — Click any lyric line to repeat, or select a range for phrase-level looping with fade-in
- **Playlist Management** — Favorites, custom playlists, import/export (M3U/M3U8)

### 📜 Lyrics
- **LRC Lyrics** — Auto-load local LRC files or fetch from online sources
- **Dual-line Display** — Current + next line with active/inactive color highlighting
- **Lyric Offset** — Fine-tune lyric timing with offset adjustment
- **Lyric Search** — Search and select from multiple lyric sources

### 📖 Study Mode
- **Media Import** — Import audio/video from local files, URLs, or WebDAV/AList
- **Subtitle Support** — Load SRT/VTT/ASS subtitles, or auto-transcribe via Whisper
- **Chapter Navigation** — Parse embedded chapters or create custom segments
- **A-B Repeat for Learning** — Repeat any sentence or paragraph with one click
- **Built-in Dictionary** — Hover over words for instant lookup (ECDict offline + online)
- **Progress Tracking** — Resume from where you left off

### 🎛️ Mini Mode
- **Compact Player** — Always-on-top mini bar with playback controls
- **Floating Lyrics** — Detachable lyric window that follows the mini bar
- **Drag & Drop** — Drag the mini bar anywhere on screen

### 🎨 Theming
- **Theme Engine** — JSON-based theme system with hot-reload
- **Built-in Themes** — Midnight Blue, Dark Purple, and more
- **Custom Themes** — Create your own themes with 50+ color tokens
- **Consistent Styling** — All UI components respect the active theme

### 🌐 Internationalization
- **Multi-language** — Chinese (zh_CN) and English (en_US) built-in
- **Extensible** — Add new languages via the i18n data module

### 🔌 Plugin System
- **Music Source Plugins** — Add new online music providers
- **Transcription Plugins** — Add speech-to-text engines (Whisper, FunASR, etc.)
- **Decoder Plugins** — Extend audio format support via BASS add-ons
- **Plugin Manager** — Install, enable/disable, and configure plugins at runtime

### 📦 Cloud & Network
- **WebDAV** — Browse and stream audio from WebDAV servers
- **AList** — Built-in AList integration for unified cloud storage access
- **Online Search** — Search across all enabled music source plugins

### ⌨️ Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `F1` | Toggle help for current page |
| `Space` | Play / Pause |
| `←` / `→` | Rewind / Forward |
| `↑` / `↓` | Volume Up / Down |

---

## 功能概览

### 🎵 音乐播放
- **本地音乐** — 目录树浏览，播放本地音频文件
- **在线音乐** — 通过插件扩展的在线音源（网易云、B站等）
- **30+ 音频格式** — MP3、WAV、FLAC、APE、OGG、M4A、AAC、WMA、OPUS、TAK、DSF 等
- **播放模式** — 顺序播放、列表循环、单曲循环、随机播放
- **A-B 复读** — 点击歌词行复读，或框选范围进行段落复读（带淡入）
- **播放列表** — 收藏夹、自定义列表、导入/导出（M3U/M3U8）

### 📖 学习模式
- **素材导入** — 本地文件、URL、WebDAV/AList 导入音视频
- **字幕支持** — SRT/VTT/ASS 字幕加载，Whisper 自动转录
- **章节导航** — 解析内嵌章节或自定义分段
- **内置词典** — 悬停查词（ECDict 离线 + 在线）
- **进度追踪** — 自动记录学习进度

### 🎛️ 迷你模式
- **精简控制条** — 置顶迷你播放条，含播放控制
- **浮动歌词** — 可分离歌词窗口，跟随迷你条定位

### 🎨 主题引擎
- **JSON 主题** — 50+ 色彩令牌，支持热重载
- **内置主题** — 午夜蓝、暗紫等
- **自定义主题** — 创建并分享你的主题

---

## Getting Started

### Prerequisites

- **Python 3.9+** (Python 3.14+ may have PySide6 compatibility issues)
- **Windows** (currently the only supported platform)
- **FFmpeg** (for audio extraction and format conversion)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/1by1OE.git
cd 1by1OE

# Install dependencies
pip install -r requirements.txt

# Install PySide6 (if not included in requirements)
pip install PySide6>=6.5.0
```

### Running

```bash
python src/main.py
```

Or after installation:

```bash
musicpp
```

### Building

```bash
# Build single executable
python build.py

# Build directory bundle
python build.py dir
```

Output will be in `dist/Music++.exe` or `dist/Music++/`.

---

## Architecture

Music++ follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────┐
│                  Presentation                    │
│   main_window · study_window · mini_window       │
│   lyric_panel · settings_panel · help_panel       │
│   online_music_panel · themed_dialog              │
├─────────────────────────────────────────────────┤
│                   Business                       │
│   playback_manager · study_manager · lyric_manager│
│   config_manager · dictionary_service · i18n      │
├─────────────────────────────────────────────────┤
│                Infrastructure                    │
│   bass_engine · theme_engine · subtitle_parser    │
│   webdav_client · alist_service · media_extractor │
│   decoder_plugin_manager · playlist_parser        │
├─────────────────────────────────────────────────┤
│                    Core                          │
│   audio_service · database_service · event_bus    │
│   metadata_service · online_music_service         │
│   search_service · download_service               │
├─────────────────────────────────────────────────┤
│                   Plugins                        │
│   plugin_interface · plugin_manager               │
│   transcription_interface · decoder plugins       │
└─────────────────────────────────────────────────┘
```

### Key Design Patterns

| Pattern | Usage |
|---------|-------|
| **Singleton** | EventBus, ConfigManager, DatabaseService, ThemeEngine, PluginManager |
| **Event Bus** | Decoupled publish/subscribe communication between layers |
| **Plugin Architecture** | Extensible music sources, transcriptions, and decoders |
| **MVC-like** | Presentation ↔ Business ↔ Core separation |

### Project Structure

```
1by1OE/
├── src/
│   ├── main.py                  # Application entry point
│   ├── core/                    # Core services (audio, database, events)
│   ├── business/                # Business logic (playback, study, lyrics)
│   ├── infrastructure/          # Infrastructure (BASS engine, WebDAV, themes)
│   ├── presentation/            # UI layer (windows, panels, dialogs)
│   ├── plugins/                 # Plugin system (interfaces, manager)
│   ├── models/                  # Data models
│   └── utils/                   # Utilities (constants, logger, icons)
├── plugins/                     # User plugins (music sources, tools)
├── bass_plugins/                # BASS audio decoder plugins
├── config/                      # Configuration & database files
├── cache/                       # Cache data (dictionaries, etc.)
├── exported_plugins/            # Exported/installable plugin packages
├── build.py                     # PyInstaller build script
├── setup.py                     # Package setup
└── requirements.txt             # Python dependencies
```

---

## Plugin Development

Music++ supports three types of plugins. Each plugin must implement the corresponding interface and include a `manifest.json`.

### 1. Music Source Plugin

Implement `MusicPluginInterface` to add a new online music provider:

```python
from src.plugins.plugin_interface import MusicPluginInterface

class MyMusicPlugin(MusicPluginInterface):
    meta = {
        "id": "my_music",
        "name": "My Music Source",
        "version": "1.0.0",
        "author": "Your Name",
        "description": "A custom music source plugin",
        "config_schema": {}
    }

    def search(self, keyword, page=1, limit=20):
        # Return: {"total": int, "list": [standardized_song_dict]}
        ...

    def get_song_url(self, song_id, quality="320k"):
        # Return: {"url": str, "headers": dict, "expires": int}
        ...

    def get_lyric(self, song_id):
        # Return: {"lrc": str, "tlyric": str}
        ...
```

**Required manifest.json:**
```json
{
    "id": "my_music",
    "name": "My Music Source",
    "version": "1.0.0",
    "type": "music_source",
    "entry": "my_music_plugin.py",
    "class": "MyMusicPlugin"
}
```

### 2. Transcription Plugin

Implement `TranscriptionInterface` to add speech-to-text capability:

```python
from src.plugins.transcription_interface import TranscriptionInterface

class MyTranscriptionPlugin(TranscriptionInterface):
    meta = {
        "id": "my_stt",
        "name": "My STT Engine",
        "version": "1.0.0",
        "author": "Your Name",
        "description": "Custom transcription plugin"
    }

    def is_available(self) -> bool: ...
    def get_models(self) -> list: ...
    def install(self, progress_callback=None) -> bool: ...
    def transcribe(self, audio_path, model_name="base", ...) -> list: ...
```

### 3. Decoder Plugin

Decoder plugins are BASS engine add-ons (DLL files) with a registry entry. See `bass_plugins/registry.json` for the format.

### Plugin Installation

1. Place the plugin folder in `plugins/` (for music source/transcription) or `bass_plugins/` (for decoders)
2. Ensure `manifest.json` is present in the plugin folder
3. Restart the application or use the Plugin Manager to reload

### Plugin Packaging

Export a plugin as a shareable package:

```
exported_plugins/
└── MyPlugin/
    ├── manifest.json
    ├── my_plugin.py
    └── (any additional files)
```

Users can install by extracting into their `plugins/` directory.

---

## Configuration

Configuration files are stored in the `config/` directory:

| File | Purpose |
|------|---------|
| `musicpp.ini` | Main application settings |
| `musicpp.db` | SQLite database (playlists, play history, study progress) |
| `online_music.json` | Online music cache |
| `decoder_plugins.json` | Decoder plugin registry |
| `themes/` | Custom theme JSON files |
| `logs/` | Application logs |

### Theme Customization

Create a JSON file in `config/themes/` with any subset of the 50+ color tokens:

```json
{
    "name": "My Theme",
    "is_dark": true,
    "colors": {
        "window_bg": "#1a1a2e",
        "accent": "#32c864",
        "text_primary": "#e0e0e0"
    }
}
```

The theme engine will merge your tokens with defaults and apply them instantly.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| GUI Framework | PySide6 (Qt for Python) |
| Audio Engine | BASS Audio Library |
| Database | SQLite3 |
| Metadata | Mutagen |
| Audio Processing | FFmpeg |
| AI Transcription | Whisper / FunASR (optional) |
| Cloud Access | WebDAV, AList |
| Build Tool | PyInstaller |
| Icon Set | Lucide (SVG) |

---

## Contributing

Contributions are welcome! Here's how you can help:

1. **Report Bugs** — Open an issue with reproduction steps
2. **Suggest Features** — Open an issue with the `enhancement` label
3. **Submit Pull Requests** — Fork, branch, and submit a PR
4. **Create Plugins** — Build and share music source, transcription, or decoder plugins
5. **Create Themes** — Design and share custom themes

### Development Setup

```bash
# Clone and install with dev dependencies
git clone https://github.com/your-username/1by1OE.git
cd 1by1OE
pip install -e ".[dev]"

# Run the application
python src/main.py
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Music++** — Reimagined with Python 🎶

</div>
