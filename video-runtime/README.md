# 视频制作共享运行代码

本目录保存制作技能依赖的局部运行代码，配合已部署的个人视频共享环境使用。入口与依赖见[工具链运行说明](../toolchain-video-production/references/runtime.md)。

- `local_tools.py`：本地 Remotion、video-use 与 FFmpeg 入口；同一次剪接处理对同一源文件复用内容哈希，新的处理重新核对。统一 `production` 入口的参数保持原样，现有 `video-use --draft` 可按需预览。
- `test_local_hash_cache.py`：3项离线针对性检查，覆盖同源/别名复用、不同源区分、跨次内容变化和未启用缓存的路径。

发布版本：20261013-v11。运行依赖包括共享 FFmpeg/FFprobe、video-use helpers、所需 Remotion/Node 与渲染浏览器；技能目录和本目录不打包这些依赖、凭据、任务状态或用户素材。
