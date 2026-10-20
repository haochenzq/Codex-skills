# 工具用法

Python 3.11及以上执行本技能scripts/organize.py，只需标准库。使用绝对输入路径；不导入构建工程、不联网、不安装或自行提权。

本机使用 `C:/Users/lenovo/AppData/Local/Programs/Python/Python313/python.exe -B -X utf8` 调用脚本；下文 `python` 均指这个已配置解释器，不按当前PATH临时切换。本工具不需要媒体环境或第三方包，缺失时修复实际解释器入口，不借用其他技能的依赖。其他设备使用已确认的Python 3.11及以上绝对路径。

```text
python <skill>/scripts/organize.py audit <root> --mode auto --depth 2 --limit 40
```

项目空间统计递归读取元数据，包含普通依赖目录的实际文件；depth仅限制明细展示和入口正文读取。返回总逻辑字节、前十目录、最大文件、生成产物线索及未统计范围，线索不等于删除授权。目录行有包含关系，不相加；硬链接计逻辑大小，不推断物理收益。链接不跟随；Codex管理分支仍省略，complete=false时不能声称全量。可选--output必须在扫描范围外且未占用，不指定则返回JSON。

默认只提取目标项目.codex/config.toml或目标所属Codex根config.toml中的相关运行位置，不回传凭据，不自动读取其他用户数据根。已授权核对的外部引用与当前在制/恢复对象通过spec.preserve登记根内相对位置。

## 计划与执行

```json
{
  "root": "D:/example-project",
  "mode": "project",
  "purpose": "已确认的空间收尾",
  "preserve": ["current-work"],
  "operations": [{
    "action": "delete", "source": "tmp/frames",
    "category": "regenerable_cache", "lifecycle": "temporary",
    "reason": "完成渲染后的中间帧",
    "evidence": "成果已验证，引用和相关进程已核对",
    "regeneration": "用户已确认无需恢复或重建"
  }]
}
```

root是绝对边界，mode为auto/project/codex；operations仍支持move、edit、delete，位置均为根内相对路径。edit提供完整UTF-8 text；move提供未占用target。删除category为regenerable_cache、obsolete_temporary或redundant_copy；三项说明必须真实；evidence可写核对结论，不要求另附证据文件，regeneration可写已确认无需恢复或重建。副本还需内容一致且未被操作的keeper。

新删除计划的lifecycle仅允许temporary或ended_test，在制/正式/恢复/未知项拒绝。ended_test还需policy指向现有项目规则文件、retained列出源目录外保留的成果；工具保存指纹并复核存在及未变，语义判断由agent依据项目与授权完成。不能为了通过检查虚报状态；不承诺丢弃测试工程后仍可精确重建。

```text
python <skill>/scripts/organize.py plan <spec.json> --output <plan.json>
python <skill>/scripts/organize.py apply <plan.json> --approved-sha256 <digest> --journal <root/本次临时目录/transaction>
python <skill>/scripts/organize.py verify <journal/receipt.json>
```

plan不改源，绑定源/目标/保留对象快照；digest不代替用户授权。越界、链接/联接、硬链接、敏感/在用对象、依赖、冲突、重叠和并发变化均拒绝。journal须根内、新建且不与操作重叠；Codex模式位于tmp内。v1历史计划/回执仍可读取和校验，新计划采用v2。

## 两种删除方式

默认staged将目录同盘暂存，核验后清除，不复制缓存；清除前可rollback，独立改写不覆盖。cleanup_pending只对同一回执finalize，不能重放apply；已清除内容只能再生成。

Windows目录暂存受阻时，核对具体范围后在独立、纯删除计划中声明method="filewise"。此模式逐文件同盘暂存并删除，遇占用/变化停止，回执记录已删数与逻辑字节；用resume <同一receipt.json>接续，不新建计划绕过防重、不删锁。无法回退已删文件；未删或暂存文件保留，不宣称可整体撤销。机器进度追加在同一事务deletions.jsonl，不重复制作备份。

只对明确的项目内node_modules/.cache/webpack数据，可附cache_kind="webpack"并使用filewise；仅接受数字/index的.pack、.pack.old或.pack.gz文件，真实依赖/程序文件与Codex管理目录仍保护。其他工程缓存沿用其原生接口或普通已审阅临时目录，不扩大这项例外。

## 验收

核对保留对象、实际入口及受影响链接；默认仅检查本次新增Markdown本地链接，历史失效路径不创建持续追踪。完成后分报迁移、实际删除、入口精简与未完成项；cleanup_pending/deletion_pending不能报告全部完成，同盘移动不算释放空间，未测量不声称磁盘增量。操作完成并核验后，回执和临时恢复副本按项目政策清理，不默认长期留存。附带脚本用于确需计划、迁移或接续的操作；简单已授权的清理可用原生工具核对具体路径后执行，不为使用脚本而额外建立事务档案。
