# 抖音下载与核验边界

## 抖音

正常路径：分享链接 → yt-dlp Douyin 提取器 → 媒体下载 → 本地验证。

`douyin_extractor_unavailable`表示提取器没有取得有效数据（上游常提示Fresh cookies，不一定需要登录）；`access_denied`、`verification_required`、`rate_limited`和明确的`login_required`分开处理。先在用户授权的Edge页面确认同一作品能播放。Edge未连接或其导出接口不可用时，可用现有内置浏览器访问同一公开页面；浏览器安全策略拒绝时停止，不用其他表面绕过。运行沙箱的DNS/文件权限限制应单独诊断，不归成平台登录故障。

若网页能公开播放，优先定位目标`video`。确认标题、作者、视频ID与时长对应用户目标，读取`currentSrc`/`source` DOM属性；不要取推荐视频。普通直接媒体用`locator.downloadMedia()`导出，再用单条源链接配合`--local-media`、`--title`、`--video-id`、`--expected-duration`入库；目标有声时加`--require-audio`。Blob地址无法由该接口直接导出时，读取[分轨备用操作](browser-streams.md)，处理已加载的画面和音轨，不反复调用Blob导出。只操作目标页面与已加载媒体，不读浏览器隐藏存储或应用内部状态。

网页本身也要求登录时，由用户完成登录。必要时由用户提供本地 Netscape 格式站点 Cookie 文件，使用 `--cookies-file <绝对路径>` 重试。脚本仅在内存使用 `douyin.com` 域 Cookie，不将完整 Cookie 写入来源记录。

不要因权限或验证码错误反复升级下载器。只有证据表明 yt-dlp 提取规则已落后时，再从 PyPI/官方仓库更新本技能独立依赖，并复验。若 Edge 页面直接提供可访问媒体地址，可用单条源链接配合 `--media-url` 下载；直链必须对应用户目标视频，不能拿缩略图或预览片段替代完整视频。

## 依赖与既有验证

独立yt-dlp依赖版本2026.8.19；本轮核对上游Douyin提取逻辑与相同Cookie错误报告，未以盲目升级代替备用路径修复。2026-10-03样例通过普通网页video导出，约32秒、1024×576；2026-10-15新增Blob音画分轨路径，验收范围见构建项目维修记录。历史记录不代表所有视频、登录高清码流或未来平台变化均可用。
