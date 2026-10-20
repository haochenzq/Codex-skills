# Codex数据边界

核对当前CODEX_HOME，默认`~/.codex`。它保存配置、认证、会话、技能和其他状态，数据库位置可单独设置。[环境变量](https://learn.chatgpt.com/docs/config-file/environment-variables)、[配置与状态](https://learn.chatgpt.com/docs/config-file/config-advanced#config-and-state-locations)。固定版本目录清单不是永久定义。

检查顶层、当前AGENTS.md、必要配置位置字段及运行引用。只提取MCP command/args/cwd等路径，不回传完整配置、env或凭据。整理无需读auth.json、密钥文件内容。日期目录和cache目录也可能是实际运行依赖。

| 类别 | 默认处理 |
| --- | --- |
| 配置、AGENTS.md、登录、凭据、应用全局状态 | 保持位置及内容 |
| SQLite/db及-wal、-shm、锁、正在写入的临时状态 | 保留，不清事务辅助文件或压缩运行中数据库 |
| sessions、archived_sessions、记忆和索引 | 保留，不靠删历史降低上下文，不改宿主生成索引 |
| skills、plugins、runtimes、浏览器、共享环境 | 按安装、调用和恢复关系保护；插件cache可能是安装代码 |
| 附件、生成图片、可视化、outputs、备份 | 核对成果、当前引用及恢复价值，不是自动垃圾 |
| 已结束任务残留、可再生缓存 | 核对无占用、无原件、无现用引用及再生成方式后按清单清理 |

应用目录不作业务式改名。插件卸载、配置/登录改变、会话删除、数据库维护和记忆内容变更是专项任务，需明确对象与授权，一般整理不包括。

执行工具在此模式只接受tmp/、.tmp/、cache/下符合证据要求的删除，不允许移改系统布局；仍检查敏感文件、配置引用、链接和硬链接。它不证明这些位置都是垃圾。其他明确授权清理由适用维护流程处理，不能换模式绕过保护。

只读审计省略会话、记忆、程序和依赖分支，说明metadata统计和省略范围，不把局部计数当总量。不读取全部会话内容。
