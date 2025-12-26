# RainyBox

本地 Web UI，用于管理 Codex、Claude Code、Qwen 的配置文件，并支持在指定工作目录中启动这些工具。

## 功能
- 首页以卡片展示工具，支持新增/编辑。
- 配置文件列表（每行一条路径）可直接编辑，多文件多文本框。
- 按工具配置启动终端、启动路径、启动命令。
- 目录浏览器用于选择启动路径。
- 工具配置保存在 `~/.rainy-box/settings.json`。

## 环境要求
- Python 3.9+

安装依赖：
```bash
pip install -r requirements.txt
```

## 运行
```bash
python app.py
```

或使用脚本：
```bash
./run.sh
```

Windows（PowerShell）：
```powershell
.\run.ps1
```

Windows（CMD）：
```bat
run.bat
```

可选环境变量：
- `PORT`（默认：8000）
- `APP_DEBUG`（默认：1）

## 默认配置文件示例
macOS：
- Codex：`~/.codex/config.toml`
- Claude Code：`~/.claude/settings.json`、`~/.claude/settings.local.json`、`~/.claude.json`
- Qwen：`~/.qwen/settings.json`

Windows 11：
- Codex：`%USERPROFILE%\\.codex\\config.toml`
- Claude Code：`%USERPROFILE%\\.claude\\settings.json`、`%USERPROFILE%\\.claude\\settings.local.json`、`%USERPROFILE%\\.claude.json`
- Qwen：`%USERPROFILE%\\.qwen\\settings.json`

## 说明
- 默认启动命令是 `codex`、`claude`、`qwen`，可在工具编辑中修改。
- 终端支持：
  - macOS：Terminal.app 或 iTerm2
  - Windows：Windows Terminal（`wt`）、PowerShell 或 CMD
