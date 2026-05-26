HELP_DATA = {
    "main_local": {
        "title": "本地音乐",
        "sections": [
            {
                "heading": "页面概述",
                "content": "本地音乐页面是 Music++ 的核心界面，用于浏览、管理和播放本地音频文件。左侧为目录树，右侧为当前目录下的音频文件列表。"
            },
            {
                "heading": "目录浏览",
                "content": (
                    "• 点击左侧目录树中的文件夹，右侧文件列表将显示该目录下的所有音频文件\n"
                    "• 展开目录节点可浏览子目录\n"
                    "• 右键点击目录：打开目录、扫描分类、复制到…、移动到…"
                )
            },
            {
                "heading": "文件列表",
                "content": (
                    "• 双击文件即可播放\n"
                    "• 列表显示：文件名、时长、格式、歌词状态\n"
                    "• 右键点击文件：\n"
                    "    - 播放：播放该文件\n"
                    "    - 搜索歌词：在线搜索并下载歌词\n"
                    "    - 浏览文件位置：在系统资源管理器中打开文件所在目录\n"
                    "    - 复制到…：将文件复制到指定目录\n"
                    "    - 移动到…：将文件移动到指定目录\n"
                    "    - 删除：删除该文件\n"
                    "    - 属性：查看文件详细信息"
                )
            },
            {
                "heading": "播放控制栏",
                "content": (
                    "• 播放/暂停：控制音频播放\n"
                    "• 快退/快进：按设定步长跳转\n"
                    "• 上一首/下一首：切换曲目\n"
                    "• 播放模式：顺序 → 列表循环 → 单曲循环 → 随机，循环切换\n"
                    "• 歌词按钮：关闭 → 歌词面板，循环切换\n"
                    "• 复读按钮：开启/关闭 AB 段复读\n"
                    "• 音源切换：本地 ↔ 在线音乐\n"
                    "• 迷你模式：切换到迷你播放器\n"
                    "• 学习模式：打开学习窗口\n"
                    "• 设置：打开设置面板"
                )
            },
            {
                "heading": "底部面板",
                "content": (
                    "• 左侧：专辑封面\n"
                    "• 中间：歌曲信息（标题、艺术家、专辑）\n"
                    "• 右侧：VU 频谱可视化\n"
                    "• 进度条：显示播放进度，可拖动跳转\n"
                    "• 音量滑块：调节音量"
                )
            },
            {
                "heading": "快捷键",
                "content": (
                    "• F1：打开/关闭帮助\n"
                    "• Space：播放/暂停\n"
                    "• 左/右方向键：快退/快进\n"
                    "• 上/下方向键：音量增减\n"
                    "• 可在设置→快捷键中自定义"
                )
            },
        ]
    },
    "main_online": {
        "title": "在线音乐",
        "sections": [
            {
                "heading": "页面概述",
                "content": "在线音乐页面支持通过音源插件搜索、播放和下载网络音乐。左侧为功能菜单，右侧为对应内容区域。"
            },
            {
                "heading": "搜索",
                "content": (
                    "• 在搜索框输入关键词后按回车或点击搜索按钮\n"
                    "• 双击搜索结果可播放\n"
                    "• 右键点击搜索结果：\n"
                    "    - 播放：立即播放\n"
                    "    - 添加到播放列表：加入当前播放队列\n"
                    "    - 收藏：添加到收藏列表\n"
                    "    - 下载：下载到本地\n"
                    "    - 匹配歌词：搜索并关联歌词\n"
                    "    - B站资源可展开章节拆分"
                )
            },
            {
                "heading": "播放列表",
                "content": (
                    "• 显示当前在线播放队列\n"
                    "• 双击播放\n"
                    "• 右键点击：收藏、匹配歌词、移除\n"
                    "• 支持清空列表和移除选中项"
                )
            },
            {
                "heading": "收藏",
                "content": (
                    "• 收藏喜爱的歌曲\n"
                    "• 支持全部播放\n"
                    "• 右键点击：播放、添加到歌单、匹配歌词、取消收藏"
                )
            },
            {
                "heading": "播放历史",
                "content": (
                    "• 自动记录播放过的在线歌曲\n"
                    "• 支持全部播放、导出历史、清空历史\n"
                    "• 右键点击：收藏、添加到歌单、匹配歌词"
                )
            },
            {
                "heading": "我的歌单",
                "content": (
                    "• 创建、重命名、删除自定义歌单\n"
                    "• 支持导入/导出歌单\n"
                    "• 右键点击歌曲：重新匹配、获取播放地址\n"
                    "• 支持从搜索结果、收藏、历史中添加歌曲"
                )
            },
        ]
    },
    "main_lyric": {
        "title": "歌词面板",
        "sections": [
            {
                "heading": "页面概述",
                "content": "歌词面板以滚动方式显示当前播放歌曲的同步歌词，支持翻译显示、偏移调整和选段复读。"
            },
            {
                "heading": "歌词显示",
                "content": (
                    "• 当前播放行高亮显示（加粗+主题色）\n"
                    "• 自动滚动跟随播放进度\n"
                    "• 支持翻译歌词双语显示"
                )
            },
            {
                "heading": "交互操作",
                "content": (
                    "• 点击歌词行：跳转到该时间点播放\n"
                    "• Shift+点击：选择多行歌词范围\n"
                    "• 选中范围后可启动 AB 段复读"
                )
            },
            {
                "heading": "偏移调整",
                "content": (
                    "• 底部偏移栏可微调歌词时间同步\n"
                    "• 点击 -2s/-1s/-0.5s/+0.5s/+1s/+2s 调整\n"
                    "• 重置按钮恢复默认偏移\n"
                    "• 保存按钮将偏移量持久化"
                )
            },
        ]
    },
    "main_settings": {
        "title": "设置",
        "sections": [
            {
                "heading": "页面概述",
                "content": "设置面板提供软件各方面的配置选项。左侧为导航菜单，右侧为对应设置内容。所有更改即时生效。"
            },
            {
                "heading": "外观",
                "content": (
                    "• 语言切换：中文/英文\n"
                    "• 窗口：总是置顶、关闭时最小化到托盘\n"
                    "• 文件列表：显示网格线、自然数排序\n"
                    "• 封面：显示/隐藏专辑封面"
                )
            },
            {
                "heading": "主题",
                "content": (
                    "• 选择预设主题或自定义编辑\n"
                    "• 支持复制、导入、导出主题（JSON格式）\n"
                    "• 迷你模式主题独立配置\n"
                    "• 可调整迷你模式透明度、字体大小、尺寸"
                )
            },
            {
                "heading": "快捷键",
                "content": "自定义播放/暂停、停止、上下曲、快退快进、音量、歌词、音源、迷你模式、设置、打开文件等快捷键。"
            },
            {
                "heading": "播放",
                "content": (
                    "• 默认播放模式：顺序/循环/单曲/随机\n"
                    "• 启动时自动播放、恢复播放位置\n"
                    "• 快退/快进步长设置\n"
                    "• 默认音量、滚轮调节音量\n"
                    "• 播放列表结束行为"
                )
            },
            {
                "heading": "音频插件",
                "content": (
                    "• 管理音频解码器插件（BASS DLL 格式）\n"
                    "• 支持导入外部解码器 DLL 文件\n"
                    "• 遇到未知格式时自动提示下载\n"
                    "• 右键点击插件：安装、卸载、查看详情"
                )
            },
            {
                "heading": "音源插件",
                "content": (
                    "• 安装、启用/禁用、删除音源插件\n"
                    "• 插件测试：搜索测试、URL测试、歌词测试\n"
                    "• 支持从文件安装插件（.py 格式）\n"
                    "• 右键点击插件：启用/禁用、测试、删除、查看详情"
                )
            },
            {
                "heading": "歌词",
                "content": (
                    "• 歌词来源排序（拖拽调整优先级）\n"
                    "• 自动下载歌词、覆盖已有歌词\n"
                    "• 时长容差设置\n"
                    "• 字体大小、颜色自定义"
                )
            },
            {
                "heading": "学习",
                "content": "配置学习模式相关参数：复读次数、复读间隔、跟读模式、自动分段参数、Whisper 语音识别等。"
            },
            {
                "heading": "WebDAV",
                "content": "配置 WebDAV 远程存储，支持数据同步和备份。"
            },
            {
                "heading": "网络",
                "content": "配置代理设置，支持 HTTP/SOCKS5 代理。"
            },
            {
                "heading": "关于",
                "content": "查看软件版本信息和相关说明。"
            },
        ]
    },
    "study_library": {
        "title": "学习 - 素材库",
        "sections": [
            {
                "heading": "页面概述",
                "content": "素材库页面管理所有导入的学习材料，包括音频/视频文件及其字幕。是学习模式的起始页面。"
            },
            {
                "heading": "素材列表",
                "content": (
                    "• 表格显示：名称、导入时间、字幕状态、学习时长、完成度\n"
                    "• 字幕状态：✓ 有字幕、⚡ 自动分段、✗ 无字幕\n"
                    "• 双击素材开始学习播放"
                )
            },
            {
                "heading": "操作按钮",
                "content": (
                    "• 播放：加载并播放该素材\n"
                    "• 重新提取字幕：从媒体文件重新提取内嵌字幕\n"
                    "• 自动分段：基于静音检测自动分割音频为句子\n"
                    "• Whisper 转录：使用 AI 语音识别生成字幕\n"
                    "• 删除：移除该素材"
                )
            },
            {
                "heading": "右键菜单",
                "content": (
                    "• 右键点击素材行可快速访问：\n"
                    "    - 播放：加载并播放\n"
                    "    - 重新提取字幕：从媒体文件提取内嵌字幕\n"
                    "    - 自动分段：基于静音检测分割\n"
                    "    - Whisper 转录：AI 语音识别生成字幕\n"
                    "    - 删除：移除该素材"
                )
            },
            {
                "heading": "批量操作",
                "content": "选择多行后可批量删除素材。"
            },
        ]
    },
    "study_import": {
        "title": "学习 - 导入素材",
        "sections": [
            {
                "heading": "页面概述",
                "content": "导入页面支持从 URL 或本地文件导入学习材料，自动提取音频和字幕。"
            },
            {
                "heading": "URL 导入",
                "content": (
                    "• 输入视频/音频 URL 地址\n"
                    "• 选择主字幕语言（en/zh/ja/ko/fr/de/es）\n"
                    "• 可选第二语言字幕\n"
                    "• 点击「导入」开始下载和提取"
                )
            },
            {
                "heading": "本地文件导入",
                "content": (
                    "• 点击「浏览」选择本地视频或音频文件\n"
                    "• 可选附加字幕文件（.srt/.ass/.vtt/.lrc）\n"
                    "• 系统会自动查找同名字幕文件\n"
                    "• 点击「导入」开始处理"
                )
            },
            {
                "heading": "批量导入",
                "content": (
                    "• 选择包含多个媒体文件的文件夹\n"
                    "• 系统自动扫描文件夹中的所有媒体文件\n"
                    "• 确认后批量导入"
                )
            },
            {
                "heading": "导入进度",
                "content": "进度条和状态文字实时显示导入进度，导入完成后自动跳转到播放。"
            },
        ]
    },
    "study_subtitle": {
        "title": "学习 - 字幕视图",
        "sections": [
            {
                "heading": "页面概述",
                "content": "字幕视图以大字体逐行显示字幕文本，适合跟读和学习。当前播放行高亮，支持单词悬停查词。"
            },
            {
                "heading": "字幕交互",
                "content": (
                    "• 点击字幕行：跳转到该句播放\n"
                    "• Ctrl+点击：多选字幕行\n"
                    "• Shift+点击：范围选择\n"
                    "• 选中后可启动区域复读\n"
                    "• 右键点击字幕行：\n"
                    "    - 复制文本：复制该行字幕文字\n"
                    "    - 从此行复读：设置复读起点\n"
                    "    - 复制时间戳：复制该行时间信息"
                )
            },
            {
                "heading": "显示模式",
                "content": (
                    "• 原文模式：仅显示原文\n"
                    "• 双语模式：原文+翻译（如有翻译字幕）"
                )
            },
            {
                "heading": "单词查词",
                "content": (
                    "• 鼠标悬停在单词上自动弹出释义\n"
                    "• 点击单词打开详细释义面板\n"
                    "• 可通过词典按钮开关查词功能"
                )
            },
            {
                "heading": "Whisper 生成",
                "content": "若无字幕，可点击「Whisper 生成字幕」按钮，使用 AI 语音识别自动生成字幕。"
            },
        ]
    },
    "study_segment": {
        "title": "学习 - 分段视图",
        "sections": [
            {
                "heading": "页面概述",
                "content": "分段视图以表格形式显示自动检测的音频分段，每个分段代表一个句子或语音片段，便于逐句学习和复读。"
            },
            {
                "heading": "分段列表",
                "content": (
                    "• 表格显示：序号、文本内容、操作\n"
                    "• 当前播放行高亮\n"
                    "• 双击分段跳转播放"
                )
            },
            {
                "heading": "操作",
                "content": (
                    "• 播放：跳转到该分段播放\n"
                    "• 复读：对该分段启动句子复读\n"
                    "• 选择多行后可启动区域复读\n"
                    "• 右键点击分段：\n"
                    "    - 播放此段：跳转播放\n"
                    "    - 复读此段：启动句子复读\n"
                    "    - 合并到上一段/下一段：合并相邻分段\n"
                    "    - 删除此段：移除该分段"
                )
            },
            {
                "heading": "自动分段",
                "content": "若无分段数据，可点击「自动分段」按钮，系统基于静音检测自动将音频分割为句子级别片段。"
            },
            {
                "heading": "视图切换",
                "content": "点击「切换视图」按钮可在字幕视图和分段视图之间切换。"
            },
        ]
    },
    "study_controls": {
        "title": "学习 - 播放控制",
        "sections": [
            {
                "heading": "播放控制栏",
                "content": (
                    "• 导入：打开导入页面\n"
                    "• 播放/暂停：控制播放\n"
                    "• 上一素材/下一素材：切换学习材料\n"
                    "• 上一句/下一句：跳转句子\n"
                    "• 复读当前句：按设定次数复读当前句子\n"
                    "• 后退5句/前进5句：快速跳转\n"
                    "• 首句/末句：跳到开头或结尾\n"
                    "• 跟读模式：播放一句后暂停等待跟读\n"
                    "• 字幕开关：显示/隐藏字幕面板\n"
                    "• 语速：0.5x ~ 2.0x 变速播放\n"
                    "• 词典开关：开启/关闭单词查词\n"
                    "• 完整模式：返回主窗口"
                )
            },
            {
                "heading": "进度条和音量",
                "content": (
                    "• 进度条：显示播放进度，可拖动跳转\n"
                    "• 时间显示：当前时间 / 总时长\n"
                    "• 音量控制：滑块调节 + 静音切换"
                )
            },
            {
                "heading": "复读状态",
                "content": "复读进行时，状态栏显示当前复读进度（如 2/3）。复读完成后自动播放下一句。"
            },
            {
                "heading": "跟读模式",
                "content": (
                    "• 开启后，每播放完一句自动暂停\n"
                    "• 暂停时间 = 句子时长 + 额外等待时间\n"
                    "• 等待时间可在设置中配置\n"
                    "• 暂停期间点击播放可跳过等待"
                )
            },
            {
                "heading": "快捷键",
                "content": (
                    "• F1：打开/关闭帮助\n"
                    "• Space：播放/暂停\n"
                    "• 左/右方向键：快退/快进 5 秒\n"
                    "• Esc：关闭学习窗口"
                )
            },
        ]
    },
    "mini_mode": {
        "title": "迷你模式",
        "sections": [
            {
                "heading": "页面概述",
                "content": "迷你模式是一个紧凑的悬浮播放控制器，始终置顶显示，适合在工作时控制音乐播放。"
            },
            {
                "heading": "控制按钮",
                "content": (
                    "• 上一首 / 播放暂停 / 下一首\n"
                    "• 歌词开关：显示/隐藏悬浮歌词窗\n"
                    "• 完整模式：返回主窗口\n"
                    "• 隐藏：隐藏迷你窗口（通过系统托盘恢复）"
                )
            },
            {
                "heading": "悬浮歌词",
                "content": (
                    "• 开启歌词后，在迷你控制器上方显示两行歌词\n"
                    "• 当前行高亮，下一行预览\n"
                    "• 可拖动移动位置"
                )
            },
            {
                "heading": "操作",
                "content": (
                    "• 拖动迷你控制器可移动位置\n"
                    "• 默认位于屏幕右下角\n"
                    "• 字体大小和颜色可在设置→主题中配置"
                )
            },
        ]
    },
    "dev_architecture": {
        "title": "开发者 - 系统架构",
        "sections": [
            {
                "heading": "项目概述",
                "content": (
                    "Music++ 是一款基于 PySide6 + BASS 音频引擎的桌面音乐播放与语言学习软件。"
                    "采用分层架构设计，核心层、业务层、基础设施层、表现层各司其职，通过事件总线解耦模块间通信。"
                )
            },
            {
                "heading": "目录结构",
                "content": (
                    "• src/core/ — 核心服务层：事件总线、数据库、搜索、下载、网络、元数据等\n"
                    "• src/business/ — 业务逻辑层：配置管理、歌词管理、播放管理、学习管理、i18n、帮助数据\n"
                    "• src/infrastructure/ — 基础设施层：BASS引擎、解码器管理、主题引擎、字幕解析、WebDAV、媒体提取\n"
                    "• src/presentation/ — 表现层：主窗口、学习窗口、迷你窗口、设置面板、歌词面板、帮助面板\n"
                    "• src/plugins/ — 插件层：音源插件接口、转录插件接口、插件管理器\n"
                    "• src/utils/ — 工具层：常量定义、日志、SVG图标、元数据数据库\n"
                    "• plugins/ — 外部音源插件目录（.py 文件）\n"
                    "• bass_plugins/ — 外部音频解码器目录（.dll 文件）\n"
                    "• config/ — 配置文件（数据库、INI配置、解码器注册表）\n"
                    "• cache/ — 缓存目录"
                )
            },
            {
                "heading": "核心设计模式",
                "content": (
                    "• 单例模式：EventBus、ConfigManager、DatabaseService、PluginManager、"
                    "DecoderPluginManager、ThemeEngine、LyricManager 等核心服务均为单例\n"
                    "• 事件驱动：模块间通过 EventBus 发布/订阅事件通信，避免直接依赖\n"
                    "• 插件架构：音源插件和转录插件通过标准接口接入，支持动态加载\n"
                    "• 分层架构：core → business → infrastructure → presentation，上层依赖下层"
                )
            },
            {
                "heading": "事件总线 (EventBus)",
                "content": (
                    "• 单例，线程安全\n"
                    "• subscribe(event_type, callback, priority) → 订阅事件，返回订阅ID\n"
                    "• unsubscribe(subscribe_id) → 取消订阅\n"
                    "• publish(event_type, data, sync) → 发布事件，支持同步/异步\n"
                    "• 主要事件常量：\n"
                    "    - EVENT_PLAYBACK_STATE_CHANGED：播放状态变化\n"
                    "    - EVENT_TRACK_CHANGED：曲目切换\n"
                    "    - EVENT_LYRIC_LOADED：歌词加载完成\n"
                    "    - EVENT_LYRIC_GENERATED：歌词生成完成\n"
                    "    - EVENT_DOWNLOAD_PROGRESS：下载进度\n"
                    "    - EVENT_PLUGIN_STATUS_CHANGED：插件状态变化\n"
                    "    - EVENT_CONFIG_UPDATED：配置更新\n"
                    "    - EVENT_PLAY_FAILED：播放失败"
                )
            },
            {
                "heading": "数据库服务 (DatabaseService)",
                "content": (
                    "• 单例，SQLite 数据库\n"
                    "• 位置：config/musicpp.db\n"
                    "• 提供 insert/update/delete/fetchone/fetchall 通用方法\n"
                    "• 主要表：plugin（插件注册）、music（音乐库）、lyric（歌词缓存）、favorite（收藏）、"
                    "playlist（歌单）、history（播放历史）、study_material（学习素材）"
                )
            },
            {
                "heading": "配置管理 (ConfigManager)",
                "content": (
                    "• 单例，INI 格式配置文件\n"
                    "• 位置：config/musicpp.ini\n"
                    "• get(section, key, default) / set(section, key, value)\n"
                    "• 主要配置节：Appearance、Playback、Lyric、Study、Network、WebDAV、Shortcuts"
                )
            },
        ]
    },
    "dev_source_plugin": {
        "title": "开发者 - 音源插件开发",
        "sections": [
            {
                "heading": "插件接口",
                "content": (
                    "所有音源插件必须继承 MusicPluginInterface（src/plugins/plugin_interface.py），"
                    "并实现以下抽象方法：\n\n"
                    "class MusicPluginInterface(ABC):\n"
                    "    meta = {\"id\", \"name\", \"version\", \"author\", \"description\", \"homepage\", \"config_schema\"}\n"
                    "    can_search: bool = True\n"
                    "    can_play: bool = True\n"
                    "    can_download: bool = True\n"
                    "    can_get_url: bool = True"
                )
            },
            {
                "heading": "必须实现的方法",
                "content": (
                    "• search(keyword, page=1, limit=20) → Dict\n"
                    "    返回：{\"total\": int, \"list\": [{\"id\", \"pluginId\", \"title\", \"artist\", \"album\", \"duration\", \"cover\", \"qualities\", \"sources\"}]}\n\n"
                    "• get_song_url(song_id, quality=\"320k\") → Dict\n"
                    "    返回：{\"url\": str, \"headers\": dict, \"expires\": int}\n\n"
                    "• get_lyric(song_id) → Dict\n"
                    "    返回：{\"lrc\": str, \"tlyric\": str}"
                )
            },
            {
                "heading": "可选覆写的方法",
                "content": (
                    "• get_download_url(song_id, quality) → 默认调用 get_song_url\n"
                    "• get_playlist(playlist_id) → 歌单功能，默认 NotImplementedError\n"
                    "• get_qualities(song_id) → 返回 [\"128k\", \"320k\"]\n"
                    "• to_standard_format(raw_data) → 将原始数据转为标准格式"
                )
            },
            {
                "heading": "meta 元信息规范",
                "content": (
                    "• id（必填）：插件唯一标识，建议格式 \"provider.module\"，如 \"netease.api\"\n"
                    "• name（必填）：插件显示名称\n"
                    "• version（必填）：版本号，如 \"1.0.0\"\n"
                    "• author（必填）：作者\n"
                    "• description：功能描述\n"
                    "• homepage：项目主页\n"
                    "• config_schema：配置项定义（JSON Schema 格式），用于设置面板动态生成配置表单"
                )
            },
            {
                "heading": "插件文件规范",
                "content": (
                    "• 文件位置：plugins/ 目录下的 .py 文件\n"
                    "• 文件名不能以 __ 开头\n"
                    "• 文件中必须包含一个且仅一个继承自 MusicPluginInterface 的类\n"
                    "• 插件类不能是 MusicPluginInterface 本身\n"
                    "• 插件通过 importlib 动态加载，无需注册"
                )
            },
            {
                "heading": "插件加载流程",
                "content": (
                    "1. PluginManager 启动时自动扫描 plugins/ 目录\n"
                    "2. 对每个 .py 文件使用 importlib 加载模块\n"
                    "3. 扫描模块中 MusicPluginInterface 的子类\n"
                    "4. 实例化插件类，读取 plugin_id\n"
                    "5. 注册到内存字典，状态设为 enabled\n"
                    "6. 持久化到数据库 plugin 表\n"
                    "7. 发布 EVENT_PLUGIN_STATUS_CHANGED 事件"
                )
            },
            {
                "heading": "搜索结果标准格式",
                "content": (
                    "每条搜索结果必须包含以下字段：\n"
                    "• id: 歌曲ID（字符串）\n"
                    "• pluginId: 插件ID（自动填充）\n"
                    "• title: 歌曲标题\n"
                    "• artist: 艺术家\n"
                    "• album: 专辑名\n"
                    "• duration: 时长（秒，整数）\n"
                    "• cover: 封面图URL\n"
                    "• qualities: [{\"level\": str, \"bitrate\": int, \"size\": int}]\n"
                    "• sources: [plugin_id]（自动填充）\n\n"
                    "可使用 to_standard_format(raw_data) 辅助转换"
                )
            },
            {
                "heading": "开发示例",
                "content": (
                    "from src.plugins.plugin_interface import MusicPluginInterface\n\n"
                    "class MySourcePlugin(MusicPluginInterface):\n"
                    "    meta = {\n"
                    "        \"id\": \"my_source\",\n"
                    "        \"name\": \"My Music Source\",\n"
                    "        \"version\": \"1.0.0\",\n"
                    "        \"author\": \"Developer\",\n"
                    "        \"description\": \"A custom music source plugin\",\n"
                    "    }\n\n"
                    "    def search(self, keyword, page=1, limit=20):\n"
                    "        results = self._do_search(keyword, page, limit)\n"
                    "        return {\"total\": len(results), \"list\": [self.to_standard_format(r) for r in results]}\n\n"
                    "    def get_song_url(self, song_id, quality=\"320k\"):\n"
                    "        url = self._get_url(song_id, quality)\n"
                    "        return {\"url\": url, \"headers\": {}, \"expires\": 3600}\n\n"
                    "    def get_lyric(self, song_id):\n"
                    "        return {\"lrc\": \"\", \"tlyric\": \"\"}"
                )
            },
            {
                "heading": "调试与测试",
                "content": (
                    "• 将 .py 文件放入 plugins/ 目录，重启软件自动加载\n"
                    "• 在设置→音源插件中查看加载状态\n"
                    "• 使用插件测试功能：搜索测试、URL测试、歌词测试\n"
                    "• 查看日志输出（控制台或日志文件）排查错误\n"
                    "• 常见问题：\n"
                    "    - 插件未加载：检查类是否继承 MusicPluginInterface\n"
                    "    - 搜索无结果：检查返回格式是否符合标准\n"
                    "    - 播放失败：检查 get_song_url 返回的 URL 是否有效"
                )
            },
        ]
    },
    "dev_decoder_plugin": {
        "title": "开发者 - 音频解码器插件",
        "sections": [
            {
                "heading": "插件类型",
                "content": (
                    "音频解码器插件基于 BASS 音频库的 DLL 扩展机制，与 Python 音源插件不同，"
                    "解码器插件是原生 DLL 文件，由 BASS 引擎直接加载调用。"
                )
            },
            {
                "heading": "插件注册表",
                "content": (
                    "解码器插件信息定义在 src/utils/constants.py 的 BASS_PLUGIN_REGISTRY 字典中：\n"
                    "• dll: DLL文件名\n"
                    "• formats: 支持的文件扩展名列表\n"
                    "• name: 显示名称\n"
                    "• description: 功能描述\n"
                    "• is_builtin: 是否内置（随软件分发）\n"
                    "• is_official: 是否 BASS 官方插件\n"
                    "• download_url: 下载地址"
                )
            },
            {
                "heading": "已注册解码器",
                "content": (
                    "• bass_aac（内置）：AAC/M4A/MP4\n"
                    "• bass_flac：FLAC 无损\n"
                    "• bass_ape：APE/MAC 无损\n"
                    "• bass_wma：WMA/WMV\n"
                    "• bass_alac：ALAC 苹果无损\n"
                    "• bass_opus：OPUS\n"
                    "• bass_mpc：Musepack\n"
                    "• bass_spx：Speex\n"
                    "• bass_tta：TTA 无损\n"
                    "• basswv：WavPack\n"
                    "• bassmidi：MIDI\n"
                    "• bass_ac3：AC3 杜比\n"
                    "• basshls：HLS 流媒体（M3U8）"
                )
            },
            {
                "heading": "添加新解码器",
                "content": (
                    "1. 获取 BASS 插件 DLL 文件（从 un4seen.com 或第三方）\n"
                    "2. 在 BASS_PLUGIN_REGISTRY 中注册插件信息\n"
                    "3. 将 DLL 放入以下位置之一：\n"
                    "    - src/infrastructure/ 目录（内置插件）\n"
                    "    - bass_plugins/ 目录（用户插件）\n"
                    "4. 重启软件，DecoderPluginManager 自动扫描加载\n"
                    "5. 也可通过设置→音频插件界面导入 DLL 文件"
                )
            },
            {
                "heading": "加载机制",
                "content": (
                    "• DecoderPluginManager（单例）管理所有解码器\n"
                    "• scan_and_load() 扫描内置和用户目录\n"
                    "• _try_load_dll() 通过 BASS 引擎加载 DLL\n"
                    "• 成功加载后，将格式映射到 _format_map\n"
                    "• can_play(ext) 检查格式是否支持\n"
                    "• get_plugin_for_format(ext) 获取对应插件\n"
                    "• 遇到未知格式时，find_missing_plugin() 查找可下载的插件"
                )
            },
            {
                "heading": "核心音频格式",
                "content": (
                    "无需插件即可播放（BASS 核心支持）：\n"
                    ".mp3, .wav, .ogg, .m4a, .aac\n\n"
                    "需要解码器插件的扩展格式：\n"
                    ".flac, .ape, .wma, .alac, .opus, .mpc, .spx, .tta, .wv, .mid, .ac3, .aiff, .dsf, .dff, .dts, .tak 等"
                )
            },
        ]
    },
    "dev_transcription_plugin": {
        "title": "开发者 - 转录插件开发",
        "sections": [
            {
                "heading": "插件接口",
                "content": (
                    "转录插件用于将音频转为字幕文本，必须继承 TranscriptionInterface"
                    "（src/plugins/transcription_interface.py）。"
                )
            },
            {
                "heading": "必须实现的方法",
                "content": (
                    "• is_available() → bool：检查依赖是否已安装\n"
                    "• get_status() → Dict：返回插件当前状态\n"
                    "• get_models() → List[Dict]：返回可用模型列表\n"
                    "• install(progress_callback) → bool：安装依赖\n"
                    "• uninstall() → bool：卸载依赖\n"
                    "• download_model(model_name, progress_callback) → bool：下载模型\n"
                    "• transcribe(audio_path, model_name, language, device, compute_type, progress_callback) → Optional[List[SubtitleLine]]：执行转录"
                )
            },
            {
                "heading": "meta 元信息",
                "content": (
                    "• id: 插件唯一标识\n"
                    "• name: 显示名称\n"
                    "• version: 版本号\n"
                    "• author: 作者\n"
                    "• description: 功能描述"
                )
            },
            {
                "heading": "SubtitleLine 数据结构",
                "content": (
                    "转录结果返回 SubtitleLine 对象列表，定义在 src/infrastructure/subtitle_parser.py：\n"
                    "• index: 序号\n"
                    "• start_ms: 开始时间（毫秒）\n"
                    "• end_ms: 结束时间（毫秒）\n"
                    "• text: 字幕文本\n"
                    "• translate: 翻译文本（可选）"
                )
            },
            {
                "heading": "参考实现：WhisperPlugin",
                "content": (
                    "src/plugins/whisper_plugin.py 是内置的 Whisper 转录插件参考实现：\n"
                    "• 基于 faster-whisper 库\n"
                    "• 支持 tiny/base/small/medium/large-v3 模型\n"
                    "• 支持自动安装依赖和下载模型\n"
                    "• 支持 GPU/CPU 自动选择\n"
                    "• 支持进度回调"
                )
            },
        ]
    },
    "dev_theme": {
        "title": "开发者 - 主题系统",
        "sections": [
            {
                "heading": "主题引擎 (ThemeEngine)",
                "content": (
                    "ThemeEngine（src/infrastructure/theme_engine.py）是单例，负责管理所有界面样式：\n"
                    "• get_current_colors() → 获取当前主题色值字典\n"
                    "• get_current_name() → 获取当前主题名称\n"
                    "• set_current_theme(name) → 切换主题\n"
                    "• generate_qss() → 生成全局 QSS 样式表\n"
                    "• 主题数据存储在 config/ 目录的 JSON 文件中"
                )
            },
            {
                "heading": "主题色值体系",
                "content": (
                    "主题通过颜色字典定义，主要键值：\n"
                    "• window_bg / surface / surface_alt：背景色层级\n"
                    "• text_primary / text_secondary / text_muted：文字色层级\n"
                    "• accent / accent_hover：强调色\n"
                    "• button_bg / button_bg_hover / button_bg_pressed：按钮色\n"
                    "• border：边框色\n"
                    "• danger / success / warning：语义色\n"
                    "• lyric_active / lyric_inactive：歌词色\n"
                    "• vu_*：VU 频谱色"
                )
            },
            {
                "heading": "创建自定义主题",
                "content": (
                    "1. 在设置→主题中选择「复制」当前主题\n"
                    "2. 编辑颜色值\n"
                    "3. 保存后立即生效\n"
                    "4. 也可通过 JSON 文件导入/导出主题\n\n"
                    "主题 JSON 格式：\n"
                    "{\n"
                    "  \"name\": \"My Theme\",\n"
                    "  \"colors\": {\n"
                    "    \"window_bg\": \"#1a1a2e\",\n"
                    "    \"accent\": \"#32c864\",\n"
                    "    ...\n"
                    "  }\n"
                    "}"
                )
            },
        ]
    },
}
