# Blob播放器的音画分轨备用

仅在目标公开作品可播放、普通video导出不支持Blob时使用。提取器、浏览器能力与站点权限是不同问题；不解验证码、不读取Cookie、不逆向签名或DRM，不抓账号/推荐流。Edge优先；其CDP等导出能力不可用时，可用内置浏览器打开同一公开作品。只有一个已加载目标且身份、时长与声音可确认时才继续。

## 取得本地清单

1. 为单个源链接打开独立任务标签，等目标video的真实时长、宽高可读。记录页面视频ID、h1标题、发布者（可读时）和完整秒数。不要只以节点顺序认定身份。
2. 读取该标签`pageAssets`和`cdp`文档，先确认导出落点符合SKILL.md暂存规则：可指定任务暂存路径，或文档确认默认使用系统任务临时目录；无法确认或只能落桌面时停止。`pageAssets.list()`可发现已加载的`media-video-avc1`或`media-video-hvc1`及`media-audio-und-mp4a`，可能分类为`other`。要求恰好一条画面轨和一条音轨；混杂时重新隔离目标，不猜配对。
3. `bundle()`不接受`other`，直接Blob导出也不支持。可仅在任务标签中用已公开的CDP DOM操作，将目标video临时换成指向这两条**已观察到URL**的video元素；这不会修改站点保存的数据。不要导航到资产URL专门取文件，也不读取应用内部状态。完成后关闭任务标签，或恢复页面。
4. 重新`pageAssets.list()`，以原两条assetId精确`bundle()`。它们此时为video类型。浏览器可能因跨域取流失败，但仍产生包含这两条来源的`manifest.json`；只输出其本地路径、计数与作品元信息，不输出完整返回对象/签名URL。文件未生成或包含额外候选时停止这条路径。

CDP DOM示例（先按当前文档取得`tab`、`assets`、`tracks`、`cdp`；`tracks`已核实属于同一目标。下面的默认`bundle()`仅在文档确认其默认落点为系统任务临时目录时使用；支持路径参数的工具按其实际文档指定，不猜参数）：

```javascript
const doc = await cdp.send('DOM.getDocument', {depth: 0});
const video = await cdp.send('DOM.querySelector', {
  nodeId: doc.root.nodeId, selector: 'video'
});
const escaped = value => value.replaceAll('&', '&amp;').replaceAll('"', '&quot;');
await cdp.send('DOM.setOuterHTML', {
  nodeId: video.nodeId,
  outerHTML: tracks.map((track, i) =>
    '<video id="capture-track-' + i + '" controls src="' + escaped(track.url) + '"></video>'
  ).join('')
});
await tab.getAXState({emit: false});
const updated = await assets.list();
const result = await assets.bundle({
  inventoryId: updated.id, assetIds: tracks.map(track => track.id)
});
nodeRepl.write({manifestPath: result.manifestPath, summary: result.summary});
```

不要把此方法用于解除工具的访问拒绝。若CDP明确不可用，不反复发送相同命令；按当前支持能力选择另一已允许的浏览器，或报告具体阻塞。任务标签中的临时DOM修改须恢复/关闭；不改用户标签、站点设置或权限。

## 下载、合并与验收

下载器单条源链接配合`--browser-manifest <本地清单>`、`--video-id <已核实ID>`、`--title <标题>`、`--expected-duration <播放器完整秒数>`和`--output <目标目录>`运行。已核实发布者可加`--author`。链接和标题依照SKILL.md安全传入，不打印清单内容。

脚本只从清单选一对HTTPS Douyin VOD来源，分别下载，在临时目录核对轨道类型及两轨与目标时长；FFmpeg以`-c copy`合并，不补帧、不改速、不用`-shortest`截断。成片须有视频和音轨，并通过时长/解码检查后才排他入库。已有同ID文件也必须满足当次完整时长与声音要求。

清单失败项只是已观察到的来源线索，不能证明下载成功；以脚本返回、音画校验及文件为准。必要时完整解码并审看/听审。签名清单仅本地短期使用，不写入来源记录、日志或版本库；确认入库后清理本任务无用清单和分轨，失败时保留仍有恢复用途的资料，不删除用户原件。
