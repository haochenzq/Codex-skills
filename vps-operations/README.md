# 个人 VPS 部署与运维

此目录整理了东京 VPS 的部署方式、Clash 分流、私人订阅和流量同步。示例 IP 为文档专用地址，使用前按自己的 VPS 填写。

| 内容 | 入口 |
| --- | --- |
| 安装 sing-box、生成凭据、防火墙、主备验证 | [部署操作手册](部署操作手册.md) |
| Hysteria2 主用、VLESS REALITY 备用、国内直连与海外代理 | [Mihomo 配置模板](clash/profile.example.yaml) |
| HTTPS 订阅、到期日和流量自动刷新、回滚 | [订阅部署与恢复](订阅部署与恢复.md) |
| 订阅、证书更新和 V.PS 用量同步 | [Python 源码](subscription/) · [systemd 单元](systemd/) |

## 使用顺序

1. 确认有供应商控制台或独立 SSH 可用，备份服务、配置和防火墙。
2. 按部署手册配置 Hysteria2 与 REALITY，先分别验证可用性，再验证自动主备。
3. 将 Clash 模板中的示例 IP、Hysteria2 密码及证书指纹、REALITY UUID、公钥和 short ID 填成实际值。东京订阅端口使用 8443。若更换端口，同步修改规则和订阅服务配置。
4. 本机执行 `mihomo -t -f profile.yaml`。订阅发布后分别核对电脑和手机，验证国内外分流及订阅 8443 经主节点可达。

Clash 模板保留了国内创作站点、Google Play 部分国内缓存的直连逻辑。阿里云国际站、Webnovel、海螺国际版及 Dreamina 按海外策略处理。BytePlus 保留业务直连例外。GeoSite 结果随客户端域名库变化，排查时以实际命中为准。

## 本地验收

使用 Python 3.10 或更新版本运行 `python -m unittest discover -s subscription -p "test_*.py"`。测试覆盖订阅认证、计数恢复、供应商用量、ACME 路径和跨周期显示。模板需在填入实际参数后验证端到端部署。
