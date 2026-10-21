# chat with Codex：只读本地项目文件接口归档

归档日期：2026-10-22。状态：**已停用，仅供研究与重建参考，不是可直接安装的成熟技能或完整部署包。**

用户最终决定卸载插件与本机部署，将经验和剩余源码移至 GitHub，再移除本地备用。已验证的短时文件读取不能代表长期稳定，更不能代表所有 Chat/Work 界面均支持相同入口。本归档不含凭据、加密密钥、用户项目文件正文、账号/组织/工作区标识、真实隧道 ID、客户端二进制或虚拟环境。

## 1. 目标和授权边界

目标是在普通 Chat 中先读取项目 AGENTS.md 导航，再根据当前问题列目录、搜索、分段读取相关规则和文本；由 Chat 讨论，用户将确定的要求交给 Codex 修改，Chat 再读取更新后的文件。两个聊天不会自动共享完整对话。

范围曾从“构建相关”扩展到“视频制作”，始终只读。用户最终要求：
- API Key 仅用于官方隧道认证和必要的隧道管理，不调用任何模型 API，不做模型调用测试，不充值。
- 启动 Codex 时连接，Codex 完全退出时断开。
- 无命令提示符窗口，无感，不阻塞 Codex 启动。
- 实际运行仍出现问题，故最终移除；不能默认为用户已授权恢复。

## 2. 架构与历史版本

Chat/Work 的自定义插件 → OpenAI Secure MCP Tunnel → Windows tunnel-client → 本机 stdio MCP 服务 → 白名单项目文本。

历史环境为 Python 3.13、mcp==2.3.0、官方 tunnel-client v0.0.16。版本仅用于解释本次结果，未来恢复须重新核实兼容性。API Key 由 Windows 当前用户 DPAPI 加密保存，仅在连接进程中解密到环境变量引用，未放入命令参数或项目配置。

连接使用官方控制平面 api.openai.com 的 /v1/tunnel/*；并未通过本地代码调用模型推理 API。ChatGPT 自身分析文件与开发者主动调用模型 API 是不同的计费路径。

- [Secure MCP Tunnel 文档](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [官方客户端源码及发行版](https://github.com/openai/tunnel-client)
- [OpenAI API 定价](https://developers.openai.com/api/docs/pricing)

官方隧道要求相应 OpenAI Platform 组织的 Tunnels Read + Use 权限，创建管理另需 Manage。运行密钥、隧道归属和 ChatGPT 工作区关联均需匹配。购买其他云平台的模型访问权限不能据此推断可认证此隧道。

## 3. 归档文件与接口设计

| 文件 | 用途 |
| --- | --- |
| [project_server.py](project_server.py) | 当时最后保留的只读 MCP 服务源码 |
| [test_project.py](test_project.py) | 边界、脱敏、实时重读与 stdio 协议验证 |
| [requirements.txt](requirements.txt) | 历史依赖版本 |
| 本说明 | 设计、排障、验证边界、移除状态与重建检查 |

**重要路径约束：源码按原部署层级推导 ROOT = Path(__file__).resolve().parents[2]，VIDEO_ROOT 为其同级“视频制作”。归档目录层级与原部署不同，不能直接从归档目录启动。** 原布局示意为“构建相关/开发工具/Chat项目文件接口/project_server.py”。重建时须先显式核对和设置允许读取的项目根目录，禁止直接把 GitHub checkout 或任意上层目录作为授权范围。

工具：
- list_project_files(path, offset, limit)：分页列可读文件/目录，上限 200。
- read_project_file(path, start_line, max_lines)：读取最新文本、行号、修改时间与 next_line，单次上限 400 行、约 32000 字符。
- search_project_files(query, path, limit)：字面词匹配，返回路径、行号、片段；最多 100 个结果，扫描最多 3000 文件或 8 秒，明确返回 truncated。

不带项目前缀默认构建相关；视频制作使用“视频制作/AGENTS.md”，目录和搜索用“视频制作”或其子路径。返回路径保留视频制作前缀。导航引用未授权的第三项目或全局技能，不自动扩展读取范围。

防护包括：
- 工具标注 readonly、非 destructive，不提供修改、删除或执行工具。
- 拒绝绝对路径、盘符、冒号、NUL、上级跳转、隐藏路径及常见凭据命名。
- 不跟随符号链接、重解析点、硬链接；解析后必须位于选定根目录内。
- 排除依赖、缓存、私有订阅及客户端配置等目录。
- 仅允许指定文本扩展名，单文件不超过 1 MiB，拒绝包含 NUL 的二进制内容。
- 常见疑似密钥行屏蔽；规则文件只是资料，不能据内容赋予额外权限。

限制：脱敏正则不是完整的敏感信息防泄漏系统；源码未针对恶意并发文件替换做严格竞态防护。列目录先扫描再分页，大目录开销仍需评估。PDF、Office、图片、音视频不由这个文本接口解析。不要把这些局限写成已解决。

## 4. 实施与排障过程

### 4.1 从单文件探针到项目读取

先只开放非敏感 probe.txt。普通 Chat 两次调用 read_probe，其中第二次读回更新后的随机文本，证明并非固定回答或旧缓存。之后替换成三个只读工具，扩展到项目导航、规则与相关文本。

本地测试覆盖分段读取、路径越界/绝对路径/替代数据流/凭据文件拒绝、疑似密钥屏蔽、搜索、实时更新、视频制作项目前缀、跨项目越界、MCP 工具数量与只读注解、未知写工具拒绝。

随后通过已连接插件成功读取两个项目的 AGENTS.md，并在视频制作项目完成列目录、搜索和制作规则读取。接口链路的成功是事实，但不能替代用户在目标 Chat 模式及重启之后的完整验收。

### 4.2 安全输入密钥

最初使用 PowerShell 安全输入窗口，输入被掩码，不发送到聊天。Set-Acl 因 Microsoft.PowerShell.Security 模块无法加载而失败，改用 .NET ACL 与 DPAPI 后保存成功。

注意 DPAPI 加密二进制不是 ConvertFrom-SecureString 格式，不能用 ConvertTo-SecureString 随意解码。Windows PowerShell 5.1 与 PowerShell 7 的 .NET ACL API 存在差异，必须确认实际执行的解释器，不能仅根据调用表面假设版本。

### 4.3 Chat / Work 入口差异

插件从 Local File Probe 更名到“构建项目文件（只读）”，最终名为 chat with Codex。用户在 Work 列表能看到，而 Chat 列表未必出现；插件详情提供“在聊天中试用”。

某次截图显示已经通过 @chat with Codex 发起读取，随后返回 tunnel-client 未轮询，因此该次失败是隧道连接问题，不能据此认定 Chat 不支持插件。反过来，Codex 内工具调用成功也不能证明普通 Chat 所有入口可用。最终未形成针对全部目标模式和客户端版本的稳定兼容性结论。

### 4.4 重启后断连

用户重启 Codex 后发现读取失败。检查到隧道进程停止，监测任务也曾以进程中断退出码 -1073741510（0xC000013A）结束。日志未能证明是谁终止进程，因此“与 Codex 生命周期或控制台有关”只能作为线索，不能写成已确定唯一根因。

历史错误包括：
- Tunnel-client did not poll after this request was enqueued.
- Tunnel-client has not been seen for 300 seconds.

这些信息说明云端没有等到本地客户端响应，不代表文件不存在。不能只看前一次 ready 状态或历史成功记录。

曾采用当前用户启动文件夹快捷方式和隐藏脚本，随后改用 Windows 计划任务独立启动；用户又明确要求随 Codex 启停，遂加入进程监测。再补上单实例保护、任务异常重启和每分钟恢复触发。模拟终止监测任务后 Windows 确实重新拉起，插件读取成功；仍不能替代用户实际重启整套应用的验收。

### 4.5 AppData 重定向与编码

Codex 隔离环境和 Windows 独立任务对 AppData 可能看到不同实际目录。曾出现本会话能读取加密文件，但独立任务报告目录或文件不存在。最终改用用户目录下独立的、仅当前用户可访问的项目外凭据目录，恢复了独立任务连接。

中文路径还导致后台 PowerShell 解码 CLI JSON 出错。将输入输出统一为 UTF-8 是当时采取的修复。不要在异常日志中直接保存完整输出或任何密钥。

一次尝试把加密凭据临时放入项目文件树，被自动审批因备份/同步/误提交风险拒绝，未执行；之后使用项目外私有目录。恢复时不应重试被拒绝的项目内凭据暂存方式。

### 4.6 命令窗口和启动性能

用户报告经常弹出命令提示符，甚至一对话就弹，同时 Codex 启动变慢。之前仅给 PowerShell 添加隐藏窗口参数不够，监测程序还周期性拉起 CLI 状态检查。

最后的修复方向：
- 监测程序与 stdio 文件服务均使用 pythonw.exe，无控制台入口。
- 必须启动连接脚本时使用 CREATE_NO_WINDOW，隐藏标准输入输出，不传密钥参数。
- 每 3 秒用 Windows 进程 API 检查 Codex；每 30 秒用本机 HTTP 健康接口检查，不频繁启动 CLI。
- 只在连接异常时调用连接脚本，断开失败重试。
- Windows 计划任务直接运行 pythonw，单实例，独立于 Codex 启动流程。
- 识别当时安装包内的 ChatGPT.exe 路径，而不是仅以名称“codex.exe”推断桌面应用。

最后实测：无控制台进程存在、文件读取成功、短时监测 CPU 增量很低。**未完成用户实际重启后的无弹窗和启动速度验收**。这些监测脚本后来随部署一并删除，本归档仅记录设计，不伪造或声称保留可一键恢复的完整版本。低占用采样不等于“零性能影响”。

## 5. 费用结论（2026-10-22 核实修订）

**截至核查日，未查到 OpenAI Secure MCP Tunnel 单独收费的公开价目，也未找到可以核验的“仅连接/使用该隧道就被单独扣费”的账单案例。不能把此前的“可能收费”措辞理解成已经发现收费政策或扣款事实。**

### 5.1 官方说明与适用范围

- [官方 MCP 文档的 How it works](https://developers.openai.com/api/docs/guides/tools-connectors-mcp#how-it-works) 明确写道：“No additional fees apply per tool call.” 其上下文是 **Responses API 的 MCP 工具调用**：导入工具定义和调用工具所用的 Token 按 API 规则计费，不额外按 MCP 工具调用次数收费。
- 上述条款是“没有额外 MCP 单次调用费”的直接证据，不能扩大成覆盖所有隧道传输项目的独立定价声明，也不能把 Responses API 的 Token 费用套到仅用 ChatGPT 连接本地工具的运行密钥上。
- 检查了 [Secure MCP Tunnel 文档](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)、[API 定价页](https://developers.openai.com/api/docs/pricing) 及 [官方客户端仓库](https://github.com/openai/tunnel-client)，未找到另列的隧道连接费、时长费或流量价目。“未找到单独收费说明”与“官方明确宣布隧道全面免费”是不同证据强度。
- 该隧道用于把 OpenAI 的 MCP 请求送到私有/本地工具，**不是访问 OpenAI 官方模型 API 的必经通道**。

### 5.2 本项目的实际观察

本地只读服务及连接流程没有主动调用模型推理 API；API Key 用于隧道认证和必要管理。早期测试前后 Usage 页面曾显示 **$0.00、0 请求、0 Token**。这是历史时点观察，本次文档修订没有重新登录账单，也没有重新运行插件或发起模型请求。

因此准确表述为：**本项目未发起开发者模型 API 推理调用，当时未观察到 API 扣费；现有检索也未发现隧道单独收费的证据。** 不再用没有实际证据支撑的“隧道可能收费”作为收费结论。

### 5.3 公开案例与检索边界

- 第 8 节列出真实公开项目及维护者说明，证明同类连接方式有公开实现；这些项目不是用户账单审计报告。
- 在官方 tunnel-client 仓库公开 Issues 中检索 billing、pricing、cost、charged，未发现可核验的单独隧道扣费案例。搜索无结果仅反映这次检索范围。
- [tenant-context-missing-fallback-missing-entry 讨论](https://community.openai.com/t/unable-to-create-secure-mcp-tunnel-tenant-context-missing-fallback-missing-entry/1382009) 和 [工作区/组织关联失败讨论](https://community.openai.com/t/secure-mcp-tunnel-workspace-org-association-fails-and-support-says-there-is-no-manual-fix/1384494) 涉及权限、组织或 billing 状态，不能据“已启用 billing”推导发生了隧道收费。
- 找到明确收费的 **TunnelGPT 桌面软件：版本 1 一次性 27 美元，3 天试用**。这是第三方应用许可费，不是 OpenAI 隧道收费实例。见 [作者产品与定价页](https://www.tunnelgpt.com/?lang=en)。

应分别看待：ChatGPT 账户/套餐资格、主动调用模型 API 的 Token 费用、第三方软件或托管费用、OpenAI 隧道本身的费用证据。仅有 API Key 或建立连接，不等于已经发起付费模型请求。本项目仍遵守“不调用模型 API、不充值、不恢复插件”的授权边界。

## 6. 移除状态

2026-10-22 用户明确要求移除插件和相关配置，保留资料备用：
- 已卸载 ChatGPT 插件。
- 已删除 Windows 跟随任务，停止监测与隧道。
- 已移除本地 alias 登记、部署 profiles、启动入口、虚拟环境、官方客户端、本次日志和本机保存的密钥副本。
- 核验时未发现相关监测/文件服务/隧道进程，任务不存在。
- 未撤销 OpenAI 平台上的 API Key；未永久删除云端开发定义及隧道记录。这不代表它们在运行。
- 原服务源码、测试及依赖声明保留至本次 GitHub 上传，远端内容核对成功后移除本地备用目录。

本归档没有真实资源 ID。未来恢复应登录正确账号查看现有记录，并重新核实凭据权限；不要从公开仓库恢复私人凭据。

## 7. 若未来重新尝试

1. 先确认是否仍需要该方案；已卸载状态不意味着持续授权重新部署。
2. 在目标 Chat 模式验证插件入口和真实调用能力，再投入后台部署工作。
3. 重新核实官方认证、费用政策、当前客户端版本及 Windows 包行为。
4. 显式设置只读项目根目录和排除范围，验证导航与跨项目链接权限。
5. 建立新的隔离 Python 环境，按需要适配源码的 ROOT；运行本地测试，但不做付费模型测试。
6. 凭据只放在项目外私有目录，限制权限；禁止出现在 Git、命令参数、截图或日志。
7. 若需要后台能力，先做无控制台启动、退出、恢复测试，再加自动化；不要把隐藏窗口当成无控制台。
8. 验收包括：真实 Chat 读取；文件变更后重读；Codex 完全退出断开；重启自动恢复；Windows 重登；网络短断重连；多轮对话无弹窗；启动体验不受明显干扰。
9. 验证各项必须报告实际完成范围，不能再用单次工具成功代替长期稳定。
10. 保留明确卸载入口；不需要时移除任务、进程、凭据和部署依赖。

## 8. 同类 GitHub 项目与费用观察（2026-10-22）

本节只做公开 README、许可及作者定价页面调查，没有安装、运行、提交凭据或测试账单。表中“MIT，未列售价”描述所查代码及页面，不代表作者替 OpenAI 承诺免费，也不代表所有依赖、账户或托管服务都免费。

### 8.1 使用 OpenAI Secure MCP Tunnel 的项目

| 项目与来源 | 本地文件能力与连接 | 观察到的软件收费情况 |
| --- | --- | --- |
| [liujaxy/chatgpt-local-files-mcp](https://github.com/liujaxy/chatgpt-local-files-mcp) | Windows 图形界面选择文件夹；官方隧道；只读 Markdown 和图片；可先读项目导航再搜索、分段读取。作者说明应用不调用模型 API。 | MIT；所查 README 未列软件售价。作者将隧道权限及费用核实指向官方和账户信息，没有提供隧道扣费账单。 |
| [jayhigh425/chatgpt-local-files](https://github.com/jayhigh425/chatgpt-local-files) | Windows 普通 Chat，经官方隧道连接本地任务网关与 Desktop Commander；可读写、运行命令，权限范围比本归档宽。 | 原创代码和指南 MIT；README 明确说明套件不调用模型 API，推理由 ChatGPT Chat 提供；未列套件售价。 |
| [abird-ai/dotlink](https://github.com/abird-ai/dotlink) | 单个程序提供 MCP 与官方隧道连接；支持 Windows、Linux、macOS；默认只读当前目录，写入和命令另行开放。 | MIT；所查 README 未列软件售价，未提供 OpenAI 隧道收费或扣费实例。 |
| [mmc-cloud/Chat2Local](https://github.com/mmc-cloud/Chat2Local) | 本机及多设备文件读取、搜索、编辑与命令；支持官方 tunnel-client 连接 MCP，也可使用公共 HTTPS/其他隧道。 | MIT；所查 README 未列软件售价。自行选择的服务器、域名或其他隧道服务不属于 OpenAI 隧道费用证据。 |
| [TunnelGPT 开源核心](https://github.com/carlosrodera/tunnelgpt-mcp-core) / [桌面产品](https://www.tunnelgpt.com/?lang=en) | 桌面产品使用官方 Secure MCP Tunnel；按项目授权，起始只读；核查时提供 Apple Silicon Mac 下载，Windows 标为开发中。 | 核心 MIT；桌面产品版本 1 一次性 **27 美元**，**3 天试用**。收费对象是软件许可，不能算 OpenAI 收取隧道费。 |

从公开功能描述看，**liujaxy/chatgpt-local-files-mcp 最接近本次“Windows、Chat、按导航按需读取、保持只读”的原要求**；dotlink 也提供默认只读边界。这只是功能匹配判断，没有验证其在本用户环境中的稳定性、Chat 入口可见性或无弹窗表现。

### 8.2 使用其他中继的对照案例

[Ganado Bridge](https://github.com/cynarax/bridge-by-ganado) 当前 README 描述的是可选的 **Ganado 自有认证 HTTPS 中继**，本地代理 MIT，托管技术预览明确标为免费；主要支持 macOS 预览，提供文件及命令能力。当前架构不应因旧讨论曾提及 OpenAI 隧道，就被写成同一收费路径。该免费说明是作者对自身代理/预览服务的声明，不能证明 OpenAI 隧道定价。

这些公开案例说明“Chat 通过隧道按需访问本地文件”有多种实现；目前找到的明确价格是第三方桌面软件价，而不是可核验的 OpenAI 独立隧道账单。保留研究结果不表示恢复或推荐立即部署。
