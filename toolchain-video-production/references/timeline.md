# 首版统一时间轴

仅在选择首版本地时间轴运行器时读取。制作项目保存一份实际 `timeline.json`，创作分镜记录意图，精确切点和文字/声音位置依据真实素材校准。它不是所有作品的强制格式；运行入口见同目录 `runtime.md`。

## 已支持字段

| 字段 | 语义 |
| --- | --- |
| `version` / `fps` / `canvas` | 示例 version=1；fps为1–60整数；canvas可填[1920,1080]或[1080,1920] |
| `assets` | ID → `{ "path": "本地文件" }`；相对路径以时间轴所在目录为基准，不支持远程URL |
| `shots` | 顺序视频段：唯一id、asset_id、in_frame、frames、可选purpose；transition仅cut |
| `titles` | text、id、start_frame、frames、可选color；frames至少12，且完整落在成片内 |
| `audio.source_gain` | 原素材声音音量，默认1，设0可静音 |
| `audio.music` | asset_id、gain及可选start_frame；音乐循环填充剩余时长 |
| `audio.voiceover` | asset_id、gain及可选start_frame；一路配音，真实时长必须容纳进成片，不允许截断 |
| `subtitles` | 可选本地SRT路径，以最终时间轴定位，画面叠加后烧录 |
| `grade` | 可选；不调色用none，其他预设按video-use入口已支持内容选择 |

总时长为 `sum(shots.frames)/fps`，所有 in_frame、frames、start_frame 都使用**时间轴的fps坐标**；例如时间轴30fps的in_frame=60表示源视频从2秒开始，即使源视频为24fps。不要把源文件帧号直接套进这里。输入素材说明中的整数秒数不是剪辑精度，先探测实际素材。

`canvas`实际传给渲染器，全部镜头按指定横竖画布等比缩放并补边；不会因首个素材朝向而改变输出尺寸。需要裁切或重新构图时明确设计，不把补边当作裁切。静帧先制作成带设计动作的视频段；相机轨迹、遮罩、复杂转场等需要在素材/其他本地合成路径完成，不添加运行器不读取的字段。

## 本地模板

下面仅示范数据结构，不规定作品长度、配音或镜头节奏。相对素材需要真实存在，替换后才能通过验证。纯音乐视频无需voiceover/subtitles；没有音乐则省略music。

```json
{
  "version": 1,
  "fps": 30,
  "canvas": [1920, 1080],
  "assets": {
    "opening": {"path": "../assets/opening.mp4"},
    "detail": {"path": "../assets/detail.mp4"},
    "score": {"path": "../assets/score.wav"}
  },
  "shots": [
    {"id": "shot_01", "asset_id": "opening", "in_frame": 0, "frames": 90, "purpose": "建立主体与空间"},
    {"id": "shot_02", "asset_id": "detail", "in_frame": 30, "frames": 60, "purpose": "动作或细节推进"}
  ],
  "titles": [
    {"id": "title_01", "text": "替换为本片文字", "start_frame": 12, "frames": 45}
  ],
  "audio": {"source_gain": 0, "music": {"asset_id": "score", "gain": 0.2}},
  "grade": "none"
}
```

## 改版与恢复

时间轴放在制作项目自己的 `edit/`，源素材另存，输出用 `film-v001.mp4`、`film-v002.mp4` 等新文件名。一个edit目录不并行渲染，避免EDL/缓存相互覆盖。

运行前 `production <timeline绝对路径> --validate` 仅核查本地素材、区间等；它不等于渲染或艺术验收，且字幕存在性等还有渲染阶段检查。生成实际成片后检查其 `.render.json`，其中保存缓存命中、输出SHA256和源文件校验值。

改一个标题可复用其他标题和视频段；改音乐可复用画面；换一个镜头只重做相关段。同次剪接处理中的同一源文件复用一次内容哈希，下一次处理仍重新计算，不依赖文件名判断素材未变。最终音画合成/编码仍会执行，不承诺任意效果或整个项目依赖图的自动局部构建。
