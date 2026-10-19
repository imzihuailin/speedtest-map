# Speedtest

使用 Ookla Speedtest 测速，保留 Omarchy 官方仪表盘，显示运营商与节点信息。从原网络面板的 **Speed Test** 按钮打开。

[English](README.md)

![预览](preview.png)

## 安装

需要 Omarchy Quattro 4.0.5+、Python 3.10+ 和 [Ookla 官方 CLI](https://www.speedtest.net/apps/cli) 1.2.0+（`speedtest`，不是 Python 的 `speedtest-cli`）。将 CLI 放入 PATH 或 `~/.local/bin/speedtest`，首次在终端运行并确认条款。

在源码目录执行：

```bash
git clone https://github.com/imzihuailin/speedtest-map.git
cd speedtest-map
python install.py
```

安装会链接源码目录并替换原测速入口，不修改系统文件。请保留源码位置；移动后重新运行安装脚本。

Esc 或点击背景停止测速，完成后按 Enter 重测。开代理时，运营商显示的是公网出口网络。

## 移除

```bash
python install.py --uninstall
```

恢复原入口，保留源码和 CLI。加 `--purge` 可清理插件配置。卸载前请保留 `~/.local/state/speedtest-map/install.json`。

## 配置

可选文件：`~/.config/speedtest-map/config.json`，支持 XDG 路径。

```json
{"cliPath":"speedtest","reducedMotion":false}
```

## 排查连接失败

如果关闭 FlClash TUN 后测速失败，请在同一个终端分别采集两份报告。先保持 TUN 开启，运行：

```bash
python tools/diagnose.py --label tun-on --output /tmp/speedtest-tun-on.json
```

手动关闭 TUN，再运行：

```bash
python tools/diagnose.py --label tun-off --output /tmp/speedtest-tun-off.json
```

重新开启 TUN 恢复连接后，比较或提供这两份 JSON 文件。重点查看 `test.phases`、`test.errors`、退出码、代理环境变量是否存在、默认路由和 DNS 状态。测速失败或报告了可恢复错误时，`serverSelection` 会提供额外的查询日志。这些记录用于排查，不会自动认定根因。终端的环境变量可能与桌面面板继承的环境不同。

工具使用已有配置中的 CLI，会执行一次真实上下行测速（最多 120 秒），产生网络流量；失败后查询服务器列表并收集详细日志（最多 30 秒）。本地检查各有独立的短超时。Ctrl+C 会停止当前子进程并保存部分报告。缺少系统命令或权限受限会记录在报告中，不影响后续检查。工具不会修改代理、路由、DNS 或桌面配置，也不会自动接受 Ookla 条款；尚未确认条款时，请先在终端手动运行官方 CLI。

报告不保存原始测速结果，会隐藏 IP、MAC、URL、代理地址及凭据，保留网卡名称和诊断信息；分享前请检查内容。报告保存成功返回退出码 0，即使测速失败也是如此；中断返回 130，保存失败返回 1。`/tmp` 中的文件可能被系统清理，需要保留时请另行复制。

## 开发

```bash
python install.py --demo    # 无需 CLI 即可安装开发
python dev.py --demo        # 离线模拟预览与源码监听
python dev.py               # 真实测速与源码监听
```

重载会重建状态栏和插件服务、关闭其他插件面板。Ctrl+C 关闭预览。

```bash
python -m unittest discover -s tests -p 'test_*.py'
node tests/model.test.cjs
omarchy plugin validate .
python tools/qml_smoke.py   # 可选：窗口集成测试
python tools/preview.py     # 用模拟数据生成 preview.png
```

[验证记录](VALIDATION.md) · [GPL-3.0-only 许可](LICENSE.md) · [第三方来源](THIRD_PARTY_NOTICES.md)
