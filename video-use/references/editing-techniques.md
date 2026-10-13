# 剪辑接口与按需技术参考

本文件只在需要EDL或特定效果时读取，不增加固定审批、转写或预览步骤。运行部署见SKILL中的统一入口；代码行为以本机helpers及Windows适配器为准。

## EDL

```json
{
  "version": 1,
  "sources": {"take1": "D:/当前作品/素材.mp4"},
  "ranges": [
    {"source": "take1", "start": 2.42, "end": 6.85,
     "quote": "保留的原话", "reason": "完整表达"}
  ],
  "overlays": [
    {"file": "D:/当前作品/edit/动画.webm", "start_in_output": 0.0, "duration": 2.0}
  ],
  "subtitles": "D:/当前作品/edit/master.srt"
}
```

`start/end`是源素材秒数，`start_in_output`是成片秒数；字幕也是成片时间。路径优先绝对路径，范围不能越界。`grade`可选预设名、原始FFmpeg滤镜或`auto`；未请求调色可省略。Windows入口支持可选`canvas`，取值依现有运行器；未指定沿用首素材朝向。不要把旁注字段当作实际渲染参数。示例的叠加、字幕按需删除，不是必填。

## 原版helpers

| 工具 | 用途与边界 |
| --- | --- |
| `helpers/render.py <EDL> -o <output>` | 原版片段提取、拼接、叠加、字幕；`--preview`、`--build-subtitles`、`--no-subtitles`详见自身帮助。本机实际渲染优先Windows适配入口。 |
| `helpers/timeline_view.py <video> <start> <end>` | 争议剪口的局部画面和波形；不逐段扫描。Windows入口`timeline`另接输出路径。 |
| `helpers/grade.py <input> -o <output>` | `--list-presets`查看已有预设，`--filter`指定滤镜。 |
| `helpers/pack_transcripts.py --edit-dir <dir>` | 兼容原版`transcripts/*.json`时打包短语视图；不是独立ASR。 |
| `helpers/transcribe.py`、`transcribe_batch.py` | 保留上游代码用于兼容；本机转写改走豆包ASR，不执行其ElevenLabs连接示例。 |

原版`render.py`的词级字幕JSON与样式有既定格式；豆包结果应由口播流程生成输出时间轴SRT，不直接假定两种JSON可互换。已有字幕优先直接引用。

## 画面、动画与声音

调色先观察代表帧，再调整确有问题的一项。ASC CDL逐通道为`out = (in * slope + offset) ** power`，随后调整饱和度；肤色及HDR源需要实际核对，不能靠预设名称证明正确。HDR到SDR必须做色调映射，不能只转换8位像素格式。

简单卡片、计数和逐字显现可用PIL/FFmpeg；精确图形与公式用Manim；已有React工程或复杂版式用Remotion。按工具链技能的选择规则复用部署，不为一张简单叠加卡新增框架。动画时长按信息量和旁白决定，最后停留按内容需要；落点与对应词或声音瞬态对齐。打字动画按完整字符串宽度固定锚点，避免逐字横移；浏览器字体等待加载并检查`document.fonts.check(...)`，PIL指定实际字体路径。

音效以瞬态而非文件起点对齐画面；配乐在语音下方让位。最终混音使用PCM中间轨，响度处理只做一次，目标沿用当前制作方案并测量输出，不重复响度标准化。画幅、分辨率、帧率与用户目标一致，不无意义放大源素材。
