# Blender GLB 接入与验收

Blender 负责制作与导出，Three.js 负责网页运行。沿用已有项目结构；下面是 Vite 原生示例的导入方式，无需新增 npm 依赖：

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import modelUrl from '../assets/model.glb?url';
const gltf = await new GLTFLoader().loadAsync(modelUrl);
scene.add(gltf.scene);
const mixer = new THREE.AnimationMixer(gltf.scene);
const clip = gltf.animations.find(clip => clip.name === wantedClip);
if (clip) mixer.clipAction(clip).play();
// 每帧以秒为单位推进；暂停时不推进。
if (playing) mixer.update(deltaSeconds);
```

`THREE`、scene、wantedClip、playing 与帧循环由当前项目提供；这不是可直接独立执行的完整程序。

## 接入约定

- `.blend` 为编辑源，GLB 为网页资产。默认米制、glTF Y-up，不能再按 Blender Z-up 旋转一遍。通过 Box3 检查实际边界与地面，取景按边界调整相机，不先任意缩放模型。物理单位或特殊原点以资产说明为准。
- Vite 的静态 `?url` 导入参与构建、生成哈希资源名并跟踪修改；使用 public URL 时尊重部署 base，重导出后主动刷新。不要让代码仅在开发时可用却遗漏构建产物。多 HTML 演示需要在构建配置中登记入口。
- 遍历 gltf.scene 获取实际网格、材质、纹理及对象名称。拾取使用递归 raycast 或收集真实子网格，父级 Group 本身不是网格。选中高亮前按需要克隆材质；导出部件可能共用同一个材质，直接改共享材质会同时改变多个部件。注意材质也可能是数组。
- 动作按名称与用途选择。只有明确独立可并播的片段才同时播放，不默认把所有互斥动作混在一起。导出帧范围、采样、根运动与循环首尾需实际检查。
- 无压缩 GLB 不需要解码器。只有资产声明对应压缩扩展时才配置 Draco、Meshopt 或 KTX2；不要为简单加载预装整套工具。
- 灯光、曝光与色调映射由网页明确配置；导出的网格不一定默认投射/接收阴影。纹理色彩空间通常由 GLTFLoader 处理，避免再次错误转换。
- 加载失败显示用户可见的状态和具体错误。反复替换模型时，卸载旧根节点、停止/释放 mixer、释放不再共享的几何/材质/纹理，避免 GPU 资源累积；普通页面重载不需要额外常驻同步服务。

## 验收闭环

按本次任务选择检查项：

1. 核对加载路径、原点、尺度、地面、纹理并截图；loaded状态不证明画面正确。
2. 涉及动画时核对片段名称、时长与实际变换；有暂停功能时检查暂停与恢复。
3. 涉及交互时实际点击部件，确认命中、高亮及相关相机操作。
4. 需要制作或返修资产时，Blender保存源文件并重导出，网页重载后确认对应变化。仅加载已有GLB时直接验收，无需为测试另改资产。
5. 检查控制台与资源错误，构建并打开产物，确认相关资产、动画和交互可用。

返修分工：几何/UV/源动画回 Blender；加载路径、取景、交互、页面逻辑改 Three.js。模型/材质交接细节见 `blender-local` 的 `references/threejs-handoff.md`（需要制作或重导出时才读取）。
