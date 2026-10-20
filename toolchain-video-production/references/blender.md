# Blender 按需制作与验收

需要三维空间、模型、材质、灯光、摄像机或三维动画时使用 Blender。二维排版继续用 Remotion，数学演示用 Manim，剪辑、音频与合成用 video-use/FFmpeg；不为每个视频启动全部工具。

## 公共入口

运行位置与依赖统一见 [RUNTIME.md](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)。以下路径均换成本次制作项目的绝对路径，正式输出使用新版本名：

```powershell
$taskVideoTools = 'C:\Users\lenovo\.codex\runtimes\personal-video\video-toolchain\video-tools.ps1'
& $taskVideoTools blender status
& $taskVideoTools blender start
# 仅尚无活动连接时，start 可带一个 .blend 路径；已有连接时不替换当前作品。
& $taskVideoTools blender render '<本项目工程.blend>' '<本项目镜头-v001.mp4>' --scene '<场景名>'
# 只在需要静帧或短段验证时选范围/缩放，正式渲染不默认降低质量。
& $taskVideoTools blender render '<本项目工程.blend>' '<本项目检查.png>' --start 24 --scale 50
& $taskVideoTools blender render '<本项目工程.blend>' '<本项目透明镜头-v001.mov>' --transparent
& $taskVideoTools blender verify '<本项目镜头-v001.mp4>' --width 1920 --height 1080 --duration 5 --frames 120
& $taskVideoTools blender verify '<本项目透明镜头-v001.mov>' --alpha
```

`render` 默认使用工程中的场景、帧区间、帧率、分辨率和引擎；`--scene` 指定场景，`--start/--end` 为包含两端的帧号。PNG 只渲染 `--start` 或场景起始帧；`--scale 1..100` 为分辨率百分比，`--samples` 和 `--engine` 仅在明确需要时改变本次渲染。视频宽高需为偶数。普通 MP4/MOV 为 H.264；透明 MOV 为 ProRes 4444，透明静帧为 RGBA PNG，MP4 不支持本入口的透明导出。

渲染使用独立后台进程，不改写源工程或关闭正在运行的 Blender。工程内合成效果保留，但本次渲染会静音合成器的文件输出节点，避免写到作品工程外的旧目录。成功后清理本次帧序列；本次失败未解决时保留必要临时目录并报告位置，解决后按公共规则收尾。输出旁生成的 `.qa.json` 与 `.render.log` 属于过程数据，按公共收尾规则处理；不覆盖已有成片。

## MCP 建场景

交互制作时，`start` 等待本机插件可用，已连接则复用。原生 MCP 从 `get_addon_status` 和 `get_scene_info` 开始；读取当前场景和保存状态，不先清空用户工程。`execute_blender_code` 负责模型、材质、灯光、相机和关键帧，`look` 按需看构图和运动。`user_prompt` 沿用用户原话。材质节点按类型查找，枚举先读取实际值；大型渲染走后台入口，不占用 MCP 单次调用。

工作期间 `.blend`、生成脚本、贴图和声音放本次制作过程目录，输出按项目归属保存；需要可移植工程时打包必要素材或保持可用相对路径。用户关闭 Blender 后，交互 MCP 需要重新启动，后台渲染仍可独立运行。库和云模型不因接入 Blender 而自动启用。

## 验收与交付

`verify` 完整解码视频，读取真实帧数、画幅、帧率、时长和音轨，并按传入规格核对；PNG 实际解码。`--alpha` 读取首帧透明通道，拒绝全不透明结果，但不证明所有帧及所有背景区域符合设计。透明背景仍需工程正确设置，地面或场景几何可能挡住背景。

交付按公共一次必要检查规则执行：`render`已自动验证输出时不再重复`verify`；内容仅抽查本次改动或明确异常，不默认检查全部关键帧或另开完整审片。源码与成片按项目用途留存；技术输出不等于已验证所有内容质量。
