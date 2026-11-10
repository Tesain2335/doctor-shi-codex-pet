# 博士士 · Codex 桌宠

<img src="assets/doctor.png" alt="博士士桌宠" width="160">

Windows 桌宠。博士士会随着鼠标在 16 个方向转头。Codex 对话完成后，带有 **VOICE** 标记的面板显示五小时额度和本轮 DeepSeek tokens，五秒后自动收起。观察到 credits 余额减少时，面板会额外显示 credits 余额。

## 安装 Windows 桌宠

1. 克隆仓库或下载 ZIP，将文件保存在一个固定的本地目录。
2. 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，并打开 PowerShell，切换到项目目录。
3. 运行下面的命令。安装器会用 uv 创建 Python 3.13 环境、安装 PySide6，并在桌面创建带博士士图标的 **Doctor-shi** 快捷方式。

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\setup.ps1
```

双击快捷方式即可启动。也可以在项目目录运行 `& .\runtime\Scripts\python.exe .\launch.py`。

如果 Windows 将下载的脚本标记为来自互联网，可先检查脚本内容，再执行 `Unblock-File -LiteralPath .\setup.ps1`。

需要登录 Windows 时自动启动，可在安装命令后加上 `-RegisterStartup`。它会注册当前用户的计划任务，登录后约 15 秒显示桌宠。用 `-NoShortcut` 可以只准备运行环境。

左键拖动可移动角色，单击可刷新额度。右键角色或托盘图标可调整大小、开关跟随、重置位置或退出。移动项目目录后，在新位置重新运行安装命令以更新快捷方式及已启用的登录任务。

## Codex Mini 宠物

将 [mini/doctor-shi](mini/doctor-shi) 整个目录复制到 `%USERPROFILE%\.codex\pets\`。目录结构应为 `pets\doctor-shi\pet.json` 和同目录的 `spritesheet.webp`。重启 Codex 后，在「设置 → Mini 与虚拟宠物」选择博士士。图集包含九组动作和十六个方向。VOICE 面板由 Windows 桌宠提供。

## 用量数据

- 五小时额度和 credits 由本机 Codex 的 app-server 提供，需要在本机登录 Codex。桌宠通过本机 Codex 会话里的完成事件触发提示。文件格式如因 Codex 更新而变化，仍可单击角色刷新。
- DeepSeek tokens 由已有的 DeepSeek Assist 用量回执提供。支持 `.codex/deepseek/usage/<thread_id>/<turn_id>/<call_id>.json`，自定义 Codex 目录时读取 `CODEX_HOME`。回执包含 `thread_id`、`turn_id`、`call_id` 和非负整数 `total_tokens`。其他客户端的调用需要写入对应回执才会计入。
- 窗口状态和启动日志位于 `%LOCALAPPDATA%\CodexPet`。窗口位置和显示设置由程序在本地生成。

## 卸载

从托盘退出桌宠。如果启用了登录任务，在项目目录运行 `& .\runtime\Scripts\python.exe .\uninstall.py`，然后删除桌面快捷方式。Mini 版本可通过移除 `pets\doctor-shi` 目录卸载。

## 素材与来源

博士士是《明日方舟》角色。本项目中的动态图集、头像和图标是同人适配。原角色与游戏素材权利归各自权利人所有。角色参考见 [明日方舟 Wiki 游戏表情一览](https://wiki.biligame.com/arknights/%E6%B8%B8%E6%88%8F%E8%A1%A8%E6%83%85%E4%B8%80%E8%A7%88)。

功能灵感来自 [DeepSeek Balance Whale Widget](https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget)。
