---
name: threejs-local
description: 创建、运行和迭代本地 Three.js 实时 3D 项目，使用现有浏览器预览、截图、验证交互和排查错误。用于 Three.js 网页开发，不用于 Blender 建模或 Remotion 视频渲染。
---

# Three.js 本地开发

查看目标项目的package.json、入口和规范，沿用框架、包管理器、锁文件及脚本。新项目可用附带的原生JavaScript＋Three.js＋Vite模板：

```powershell
node "<技能目录>/scripts/create-project.mjs" "<新项目绝对路径>"
Set-Location -LiteralPath "<新项目绝对路径>"
npm ci --no-fund
npm run dev
```

创建脚本只复制文件，拒绝覆盖已有目标，不自动安装或启动。模板依赖锁在package-lock.json并留在项目内，不借视频共享环境，也不为套模板引入React。

## 开发与验证

- 按项目脚本启动并保留终端会话。模板只监听本机，开发`http://127.0.0.1:5173/`，预览`http://127.0.0.1:4173/`；冲突时核对占用并用`-- --port <空闲端口>`，不结束未知进程。
- 复用当前浏览器工具及已确认能力，遵循其接口；仅功能缺口明确时增加依赖，无需预装Playwright MCP。
- 按改动检查实际画面、控制台和相关动画、相机、点选、适配。模板`#diagnostics`包含WebGL、帧数、动画时间、相机位置、选中次数、错误和绘制统计，仅作辅助；HTTP成功、构建通过或诊断文本不能代替截图与实际交互。点选按当前画面定位，canvas中心不保证命中。
- Vite自动重载后核对新状态；必要时启用错误采集再刷新，用新页或导航时间区分历史错误。尺寸变化核对布局和画布；性能仅前台采样，不将后台限速当GPU性能或依赖固定CDP接口。
- 按日志修复并复验相关功能；仅明确要求时在可控示例注入可撤销故障。按项目脚本构建并按需预览，模板用`npm run build`、`npm run preview`；500 kB提示不自动触发小示例拆包或调高告警阈值。

## 资产与交付

加载Blender/glTF时读[GLB接入与验收](references/blender-handoff.md)。几何、UV、PBR材质和源动画需返修时接续`blender-local`；网页加载、相机和交互在此处理，GLB运行无需Blender在线。

简报实测结果与限制，按需提供截图和预览地址；保留交付所需页面与服务，其余本次临时页面和进程用原会话关闭。项目可独立用npm运行，本技能不提供后台自动修复。
