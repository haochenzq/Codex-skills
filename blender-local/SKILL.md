---
name: blender-local
description: 通过现有本地 Blender MCP 检查和编辑场景，进行建模、材质、灯光与动画制作，并按需导出 GLB 供 Three.js 使用。适用于 Blender 资产制作，不替代网页交互开发或 Remotion 视频流程。
---

# 本地 Blender

复用现有 MCP 制作资产；普通建模、动画和GLB导出无需云API。

## 连接与场景

- 用`get_addon_status`、`get_scene_info`核对版本、连接和场景，读取返回文本中的错误。本机Blender 4.5.9 LTS：`D:/Program Files/Blender/blender-4.5.9-windows-x64/blender.exe`；启动：`D:/BlenderMCP/启动Blender.cmd`；插件端口：`127.0.0.1:9876`。
- 离线先区分程序未运行、插件未监听或MCP故障；按需启动既有程序，不例行重装、升级、改配置，不多开实例抢端口或强杀未知进程。
- 用`execute_blender_code`读取`bpy.data.filepath`、`bpy.data.is_dirty`、场景、模式与选择。局部修改既有作品，演示用独立场景或集合；不清空启动场景或覆盖未保存工作。新文件可用`save_as_mainfile(copy=True)`保留当前文件身份；导出前保护选择、模式、帧和场景，之后按需恢复。
- 路径或端口变化时，核对当前MCP配置的command、args及插件监听设置，复用实际入口；无需读取构建项目资料。

## 制作与交接

- 优先用MCP Python局部修改，打印关键对象、尺寸和输出位置；`user_prompt`填用户原话。
- Shader节点按`node.type`识别，渲染颜色改Principled BSDF输入，不只改`diffuse_color`。参数查当前RNA/接口；动态枚举为空时查实际导出器声明，不猜值。
- 用`look`或渲染截图核对材质、视角和动画，不能只看代码是否报错；按需交付资产，可编辑`.blend`是否交付或留存按本次要求与项目规则确定。
- 第三方素材库和生成器默认关闭；明确要求外部服务时再核对授权、成本与工具，不自动上传或读取凭据。
- 网页资产读取[GLB交接](references/threejs-handoff.md)：Blender负责几何、UV、材质和源动画，`threejs-local`负责网页运行、相机、交互及浏览器验收，可在同一任务接续。
