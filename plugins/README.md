# 洛雪音乐数据源文件说明

## 文件概述

本目录包含用于洛雪音乐桌面版的网易云音乐数据源插件文件。

## 文件列表

### 1. `lx_netease_source.js` - 主数据源文件

这是洛雪音乐桌面版可用的实际音乐源JS文件,具有以下特点:

#### 功能特性

✅ **搜索功能**
- 使用网易云音乐官方API进行歌曲搜索
- 支持分页查询
- 返回完整的歌曲信息(歌名、艺术家、专辑、时长等)

✅ **获取歌曲URL**
- 支持多种音质: 128k, 320k, flac
- 使用网易云音乐API获取真实的播放地址

✅ **获取歌词**
- 获取歌曲歌词(lrc格式)
- 支持翻译歌词
- 返回歌词贡献者信息

✅ **获取专辑封面**
- 通过歌曲ID获取专辑封面图片URL

✅ **其他功能**
- 歌手信息查询
- 专辑信息查询
- 歌手热门歌曲查询
- 专辑歌曲列表查询
- 推荐歌曲
- 排行榜列表
- 排行榜详情
- 热搜词
- 搜索建议

#### 技术实现

- **源ID**: `wy`
- **源名称**: `网易云音乐`
- **全局API**: 使用洛雪音乐规定的 `globalThis.lx` 全局对象
- **事件驱动**: 监听 `EVENT_NAMES.request` 事件
- **初始化**: 通过 `EVENT_NAMES.inited` 事件注册源信息
- **错误处理**: 全面的try-catch和错误返回机制
- **HTTP请求**: 使用洛雪音乐内置的 `request` 函数

#### API端点

```javascript
const BASE_URL = 'https://music.163.com';

const SEARCH_URL = `${BASE_URL}/api/search/get/post`;
const SONG_URL_API = `${BASE_URL}/api/song/enhance/player/url`;
const LYRIC_URL = `${BASE_URL}/api/song/lyric`;
const SONG_DETAIL_URL = `${BASE_URL}/api/v1/song/detail`;
```

### 2. `test_lx_source.py` - Python验证脚本

用于验证JS文件结构完整性的Python脚本。

**使用方法:**
```bash
python test_lx_source.py
```

**验证内容:**
- 文件头部元数据
- 必要的全局变量引用
- 源ID和源名称
- 功能函数存在性
- API URL配置
- 事件监听和初始化
- 音质支持
- 错误处理机制

### 3. `test_js_syntax.js` - Node.js语法验证脚本

用于检查JavaScript语法和代码质量的Node.js脚本。

**使用方法:**
```bash
node test_js_syntax.js
```

**验证内容:**
- 基本语法结构
- 核心组件完整性
- API端点配置
- 事件处理逻辑
- 错误处理机制
- 代码质量指标
- 安全性检查

## 使用说明

### 安装步骤

1. **定位洛雪音乐数据源目录**
   - Windows: `%APPDATA%/lx-music-desktop/resources/data/source`
   - Mac: `~/Library/Application Support/lx-music-desktop/resources/data/source`
   - Linux: `~/.config/lx-music-desktop/resources/data/source`

2. **复制源文件**
   ```bash
   cp lx_netease_source.js <洛雪音乐数据源目录>/
   ```

3. **重启洛雪音乐**

4. **启用数据源**
   - 打开洛雪音乐设置
   - 找到"音乐源"或"数据源"选项
   - 启用"网易云音乐"源

### 测试步骤

1. **运行Python验证脚本**
   ```bash
   cd plugins
   python test_lx_source.py
   ```

2. **运行Node.js语法检查**
   ```bash
   node test_js_syntax.js
   ```

3. **在洛雪音乐中测试**
   - 尝试搜索歌曲(如"周杰伦 晴天")
   - 点击播放测试音质切换
   - 查看歌词是否正常显示
   - 检查专辑封面是否加载

## 数据结构

### 歌曲信息格式

```javascript
{
  id: String,          // 歌曲ID
  name: String,       // 歌曲名称
  artist: String,     // 艺术家(多个用逗号分隔)
  album: String,      // 专辑名称
  albumId: String,    // 专辑ID
  duration: Number,   // 时长(秒)
  source: 'wy',       // 数据源ID
  sourceName: String, // 数据源名称
  copyrightId: String,// 版权ID
  picUrl: String,      // 封面URL
  lyric: String,      // 歌词
  tlyric: String      // 翻译歌词
}
```

### 请求处理

```javascript
on(EVENT_NAMES.request, async({ source, action, info }) => {
  if (source !== 'wy') return;

  const result = await handleRequest(action, info);

  send(EVENT_NAMES.request, {
    source,
    action,
    info,
    response: result
  });
});
```

### 支持的请求类型

| Action | 描述 | 参数 |
|--------|------|------|
| search | 搜索歌曲 | text, page, limit |
| musicUrl | 获取歌曲URL | musicInfo, quality |
| lyric | 获取歌词 | musicInfo |
| pic | 获取封面 | musicInfo |
| album | 获取专辑信息 | albumId |
| artist | 获取歌手信息 | artistId |
| artistSongs | 获取歌手歌曲 | artistId, page, limit |
| albumSongs | 获取专辑歌曲 | albumId |
| recommend | 推荐歌曲 | - |
| topList | 排行榜列表 | - |
| topListDetail | 排行榜详情 | topListId, page, limit |
| hotSearch | 热搜词 | - |
| searchSuggest | 搜索建议 | keyword |

## 注意事项

⚠️ **网络要求**
- 需要稳定的网络连接
- 网易云音乐API可能有访问限制

⚠️ **Cookie要求**
- 部分高级功能可能需要登录Cookie
- 建议使用浏览器开发者工具获取Cookie

⚠️ **音质限制**
- 部分歌曲可能不支持高音质
- FLAC音质需要VIP账号

⚠️ **API稳定性**
- 网易云音乐API可能随时变更
- 建议关注官方API更新

## 故障排查

### 问题1: 搜索无结果

**解决方案:**
1. 检查网络连接
2. 确认API是否可访问
3. 查看浏览器控制台错误信息

### 问题2: 无法获取播放URL

**解决方案:**
1. 歌曲可能需要VIP权限
2. 尝试切换到较低音质
3. 更新Cookie信息

### 问题3: 歌词获取失败

**解决方案:**
1. 部分歌曲可能没有歌词
2. 检查网络连接
3. 可能是版权限制

### 问题4: 封面无法加载

**解决方案:**
1. 检查图片URL是否有效
2. 确认CDN是否可访问
3. 使用代理服务器

## 更新日志

### v1.0.0 (2026-05-12)
- ✨ 初始版本发布
- ✅ 实现搜索功能
- ✅ 实现歌曲URL获取
- ✅ 实现歌词获取
- ✅ 实现封面获取
- ✅ 支持128k/320k/FLAC音质
- ✅ 实现排行榜功能
- ✅ 实现热搜词功能

## 贡献指南

欢迎提交Issue和Pull Request来改进这个数据源。

## 许可证

本项目遵循洛雪音乐桌面版的开源协议。

## 联系方式

- GitHub: https://github.com/example/lx-music-source
- 问题反馈: 请在GitHub Issues中提交

## 参考资源

- [洛雪音乐桌面版](https://github.com/lyswhut/lx-music-desktop)
- [网易云音乐API文档](https://github.com/Binaryify/NeteaseCloudMusicApi)
- [洛雪音乐源文件规范](https://github.com/lyswhut/lx-music-desktop/issues)
