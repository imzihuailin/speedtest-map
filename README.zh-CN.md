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
