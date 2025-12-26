"""RainyBox：本地管理多工具配置文件与启动入口的轻量 Web 应用。"""

import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import toml
from flask import Flask, abort, flash, redirect, render_template, request, url_for

# 应用配置与默认存储位置
APP_NAME = "RainyBox"
SETTINGS_DIR = Path.home() / ".rainy-box"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

# 各系统可用终端列表
TERMINAL_OPTIONS = {
    "Darwin": [
        ("terminal", "Terminal.app"),
        ("iterm", "iTerm2"),
    ],
    "Windows": [
        ("wt", "Windows Terminal"),
        ("powershell", "PowerShell"),
        ("cmd", "Command Prompt"),
    ],
}


def terminal_choices():
    return TERMINAL_OPTIONS.get(platform.system(), [])


def default_terminal():
    options = terminal_choices()
    return options[0][0] if options else ""


def terminal_label_map():
    return {key: label for key, label in terminal_choices()}


def default_tools():
    """内置的默认工具列表。"""
    terminal = default_terminal()
    return [
        {
            "id": "codex",
            "name": "Codex",
            "config_files": ["~/.codex/config.toml"],
            "launch_terminal": terminal,
            "launch_path": "~",
            "launch_command": "codex",
        },
        {
            "id": "claude",
            "name": "Claude Code",
            "config_files": [
                "~/.claude/settings.json",
                "~/.claude/settings.local.json",
                "~/.claude.json",
            ],
            "launch_terminal": terminal,
            "launch_path": "~",
            "launch_command": "claude",
        },
        {
            "id": "qwen",
            "name": "Qwen",
            "config_files": ["~/.qwen/settings.json"],
            "launch_terminal": terminal,
            "launch_path": "~",
            "launch_command": "qwen",
        },
    ]


def _normalize_tool(tool):
    """标准化工具配置，补齐缺省字段。"""
    terminal = default_terminal()
    launch_path = tool.get("launch_path")
    if launch_path is None:
        launch_path = "~"
    normalized = {
        "id": tool.get("id") or str(uuid.uuid4()),
        "name": tool.get("name") or "未命名工具",
        "config_files": tool.get("config_files") or [],
        "launch_terminal": tool.get("launch_terminal") or terminal,
        "launch_path": launch_path,
        "launch_command": tool.get("launch_command") or "",
    }
    if isinstance(normalized["config_files"], str):
        normalized["config_files"] = [normalized["config_files"]]
    normalized["config_files"] = [
        str(item).strip() for item in normalized["config_files"] if str(item).strip()
    ]
    return normalized


def load_tools():
    """从本地 JSON 读取工具列表，异常时回退到默认工具。"""
    if not SETTINGS_PATH.exists():
        return default_tools()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_tools()
    tools = data.get("tools")
    if not isinstance(tools, list):
        return default_tools()
    return [_normalize_tool(tool) for tool in tools]


def save_tools(tools):
    """保存工具列表到本地 JSON 文件。"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"tools": tools}
    SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_tool(tool_id):
    """按 id 查找工具。"""
    for tool in load_tools():
        if tool["id"] == tool_id:
            return tool
    return None


def expand_path(path_str):
    """展开 ~ 和环境变量，并保证返回绝对路径。"""
    raw = os.path.expandvars(str(path_str))
    expanded = Path(raw).expanduser()
    if not expanded.is_absolute():
        expanded = Path.home() / expanded
    return expanded


def detect_format(path_str):
    """根据后缀识别配置文件格式。"""
    suffix = Path(str(path_str)).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    return "text"


def load_file_content(path, file_type):
    """读取文件内容并做格式校验。"""
    if not path.exists():
        return "", "文件不存在，保存后将创建。"
    content = path.read_text(encoding="utf-8", errors="replace")
    if file_type == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return content, f"JSON 无效：{exc}"
    if file_type == "toml":
        try:
            toml.loads(content)
        except toml.TomlDecodeError as exc:
            return content, f"TOML 无效：{exc}"
    return content, None


def validate_content(file_type, content):
    """保存前做格式校验。"""
    if file_type == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return f"JSON 无效：{exc}"
    if file_type == "toml":
        try:
            toml.loads(content)
        except toml.TomlDecodeError as exc:
            return f"TOML 无效：{exc}"
    return None


def write_content(path, content):
    """写入文件内容，必要时创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def escape_applescript(value):
    """AppleScript 字符转义。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def launch_on_macos(terminal_key, cwd, command):
    """macOS 终端启动逻辑，保持窗口不关闭。"""
    quoted_path = escape_applescript(str(cwd))
    quoted_command = escape_applescript(command)
    if terminal_key == "iterm":
        script = (
            'tell application "iTerm"\n'
            "  activate\n"
            "  if (count of windows) = 0 then\n"
            "    create window with default profile\n"
            "  end if\n"
            "  tell current session of current window\n"
            f'    write text "cd {quoted_path}; {quoted_command}; exec $SHELL"\n'
            "  end tell\n"
            "end tell"
        )
    else:
        script = (
            'tell application "Terminal"\n'
            "  activate\n"
            f'  do script "cd {quoted_path}; {quoted_command}; exec $SHELL"\n'
            "end tell"
        )
    subprocess.Popen(["osascript", "-e", script])


def escape_windows(value):
    """Windows 命令行字符转义。"""
    return value.replace('"', '\\"')


def launch_on_windows(terminal_key, cwd, command):
    """Windows 终端启动逻辑，保持窗口不关闭。"""
    cwd_str = str(cwd)
    escaped_cwd = escape_windows(cwd_str)
    escaped_cmd = escape_windows(command)
    if terminal_key == "wt":
        subprocess.Popen(
            ["wt", "-d", cwd_str, "cmd", "/k", command],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return
    if terminal_key == "powershell":
        command_line = (
            f'start "RainyBox" powershell -NoExit -Command '
            f'"cd /d \\"{escaped_cwd}\\"; {escaped_cmd}"'
        )
    else:
        command_line = f'start "RainyBox" cmd /k "cd /d {escaped_cwd} && {escaped_cmd}"'
    subprocess.Popen(["cmd", "/c", command_line], shell=False)


def launch_tool(terminal_key, cwd, command):
    """按系统分发启动逻辑。"""
    system = platform.system()
    if system == "Darwin":
        launch_on_macos(terminal_key, cwd, command)
        return
    if system == "Windows":
        launch_on_windows(terminal_key, cwd, command)
        return
    raise RuntimeError(f"不支持的系统：{system}")


def list_directory(path):
    """列出目录下的子目录。"""
    entries = []
    try:
        for entry in path.iterdir():
            if entry.is_dir():
                entries.append(entry)
    except PermissionError:
        return []
    return sorted(entries, key=lambda p: p.name.lower())


def list_directory_items(path):
    """列出目录下的子目录与文件。"""
    dirs = []
    files = []
    try:
        for entry in path.iterdir():
            if entry.is_dir():
                dirs.append(entry)
            elif entry.is_file():
                files.append(entry)
    except PermissionError:
        return [], []
    return sorted(dirs, key=lambda p: p.name.lower()), sorted(files, key=lambda p: p.name.lower())


def root_candidates():
    """获取系统根目录候选。"""
    system = platform.system()
    if system == "Windows":
        roots = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            if drive.exists():
                roots.append(drive)
        return roots
    return [Path("/"), Path.home()]


def is_frozen():
    """判断是否运行在 PyInstaller 打包环境中。"""
    return getattr(sys, "frozen", False)


def configure_frozen_runtime():
    """打包环境下重定向输出，避免无控制台时报错。"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SETTINGS_DIR / "rainybox.log"
    log_file = log_path.open("a", encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file


def find_available_port(start_port, host="127.0.0.1", max_tries=20):
    """从指定端口开始查找可用端口。"""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return port
    return start_port


def start_server_in_background(host, port):
    """后台启动 Flask 服务。"""
    thread = threading.Thread(
        target=app.run,
        kwargs={
            "host": host,
            "port": port,
            "debug": False,
            "use_reloader": False,
        },
        daemon=True,
    )
    thread.start()
    return thread


def wait_for_server(host, port, timeout=5.0):
    """等待服务就绪，避免 WebView 空白。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def normalize_picker_mode(mode):
    """限制选择器模式：file/dir。"""
    return mode if mode in {"file", "dir"} else "file"


def build_picker_context(path_arg, mode):
    """构建文件/目录选择器的展示数据。"""
    selected_file = None
    current = Path.home()
    if path_arg:
        candidate = Path(path_arg).expanduser()
        if candidate.is_file():
            if mode == "file":
                selected_file = candidate
            candidate = candidate.parent
        if not candidate.exists() or not candidate.is_dir():
            flash("目录不存在，已返回主目录。", "warning")
            candidate = Path.home()
        current = candidate

    parent = current.parent if current.parent != current else None
    dirs, files = list_directory_items(current)
    input_path = str(selected_file or current) if mode == "file" else str(current)
    selected_value = str(selected_file) if mode == "file" and selected_file else ""

    return {
        "current": current,
        "parent": parent,
        "dirs": dirs,
        "files": files,
        "home": Path.home(),
        "mode": mode,
        "input_path": input_path,
        "selected_file": selected_value,
    }


def parse_config_files(text):
    """解析配置文件列表文本（按行）。"""
    lines = [line.strip() for line in text.splitlines()]
    files = []
    seen = set()
    for line in lines:
        if not line or line in seen:
            continue
        seen.add(line)
        files.append(line)
    return files


def config_files_text(files):
    """配置文件列表转为多行文本。"""
    return "\n".join(files or [])


def build_config_entries(tool, override=None):
    """构建配置文件编辑器需要的上下文。"""
    entries = []
    for path_str in tool["config_files"]:
        file_type = detect_format(path_str)
        abs_path = expand_path(path_str)
        if override and override.get("path") == path_str:
            content = override.get("content", "")
            error = override.get("error")
        else:
            content, error = load_file_content(abs_path, file_type)
        entries.append(
            {
                "path": path_str,
                "abs_path": abs_path,
                "file_type": file_type,
                "content": content,
                "error": error,
                "exists": abs_path.exists(),
            }
        )
    return entries


# Flask 应用与路由
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "local-dev-secret")


@app.context_processor
def inject_globals():
    return {"app_name": APP_NAME}


@app.route("/")
@app.route("/configs")
def home():
    """首页：工具卡片列表。"""
    tools = load_tools()
    return render_template(
        "home.html",
        tools=tools,
        terminal_labels=terminal_label_map(),
    )


@app.route("/tools/new", methods=["GET", "POST"])
def tool_new():
    """新增工具。"""
    terminals = terminal_choices()
    terminal_keys = {key for key, _ in terminals}
    errors = []
    data = {
        "name": "",
        "config_files": [],
        "launch_terminal": default_terminal(),
        "launch_path": request.args.get("path", ""),
        "launch_command": "",
    }

    if request.method == "POST":
        data["name"] = request.form.get("name", "").strip()
        data["launch_command"] = request.form.get("launch_command", "").strip()
        data["launch_path"] = request.form.get("launch_path", "").strip()
        data["launch_terminal"] = request.form.get("launch_terminal", "").strip()

        # 去重并保序
        raw_files = [item.strip() for item in request.form.getlist("config_files") if item.strip()]
        seen = set()
        config_files = []
        for path in raw_files:
            if path in seen:
                continue
            seen.add(path)
            config_files.append(path)
        data["config_files"] = config_files
        if not data["name"]:
            errors.append("工具名称不能为空。")
        if data["launch_terminal"] not in terminal_keys:
            data["launch_terminal"] = default_terminal()

        if not errors:
            tools = load_tools()
            tools.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": data["name"],
                    "config_files": config_files,
                    "launch_terminal": data["launch_terminal"],
                    "launch_path": data["launch_path"],
                    "launch_command": data["launch_command"],
                }
            )
            save_tools(tools)
            flash("工具已新增。", "success")
            return redirect(url_for("home"))

    context = {
        "mode": "new",
        "title": "新增工具",
        "data": data,
        "terminals": terminals,
        "errors": errors,
    }
    return render_template("tool_form.html", **context)


@app.route("/tools/<tool_id>/edit", methods=["GET", "POST"])
def tool_edit(tool_id):
    """编辑工具。"""
    terminals = terminal_choices()
    terminal_keys = {key for key, _ in terminals}
    tool = find_tool(tool_id)
    if not tool:
        abort(404)

    errors = []
    data = {
        "name": tool["name"],
        "config_files": tool["config_files"],
        "launch_terminal": tool["launch_terminal"],
        "launch_path": request.args.get("path", tool.get("launch_path") or ""),
        "launch_command": tool["launch_command"],
    }

    if request.method == "POST":
        data["name"] = request.form.get("name", "").strip()
        data["launch_command"] = request.form.get("launch_command", "").strip()
        data["launch_path"] = request.form.get("launch_path", "").strip()
        data["launch_terminal"] = request.form.get("launch_terminal", "").strip()

        # 去重并保序
        raw_files = [item.strip() for item in request.form.getlist("config_files") if item.strip()]
        seen = set()
        config_files = []
        for path in raw_files:
            if path in seen:
                continue
            seen.add(path)
            config_files.append(path)
        data["config_files"] = config_files
        if not data["name"]:
            errors.append("工具名称不能为空。")
        if data["launch_terminal"] not in terminal_keys:
            data["launch_terminal"] = default_terminal()

        if not errors:
            tools = load_tools()
            updated = []
            for item in tools:
                if item["id"] != tool_id:
                    updated.append(item)
                    continue
                updated.append(
                    {
                        "id": item["id"],
                        "name": data["name"],
                        "config_files": config_files,
                        "launch_terminal": data["launch_terminal"],
                        "launch_path": data["launch_path"],
                        "launch_command": data["launch_command"],
                    }
                )
            save_tools(updated)
            flash("工具已更新。", "success")
            return redirect(url_for("home"))

    context = {
        "mode": "edit",
        "title": f"编辑 {tool['name']}",
        "data": data,
        "terminals": terminals,
        "errors": errors,
        "tool_id": tool_id,
    }
    return render_template("tool_form.html", **context)


@app.post("/tools/<tool_id>/delete")
def tool_delete(tool_id):
    """删除工具。"""
    tools = load_tools()
    tool = next((item for item in tools if item["id"] == tool_id), None)
    if not tool:
        abort(404)
    remaining = [item for item in tools if item["id"] != tool_id]
    save_tools(remaining)
    flash(f"已删除 {tool['name']}", "success")
    return redirect(url_for("home"))


@app.route("/tools/<tool_id>/configs", methods=["GET", "POST"])
def tool_configs(tool_id):
    """配置文件编辑页。"""
    tool = find_tool(tool_id)
    if not tool:
        abort(404)

    if request.method == "POST":
        file_path = request.form.get("file_path", "").strip()
        if file_path not in tool["config_files"]:
            abort(400)
        content = request.form.get("content", "")
        file_type = detect_format(file_path)
        error = validate_content(file_type, content)
        if error:
            entries = build_config_entries(tool, {"path": file_path, "content": content, "error": error})
            return render_template(
                "tool_configs.html",
                tool=tool,
                entries=entries,
            )
        write_content(expand_path(file_path), content)
        flash(f"已保存 {file_path}", "success")
        return redirect(url_for("tool_configs", tool_id=tool_id))

    entries = build_config_entries(tool)
    return render_template(
        "tool_configs.html",
        tool=tool,
        entries=entries,
    )


@app.post("/tools/<tool_id>/launch")
def tool_launch(tool_id):
    """启动工具。"""
    tool = find_tool(tool_id)
    if not tool:
        abort(404)

    # 启动命令与路径为空时，在这里提示用户
    command = tool["launch_command"].strip()
    if not command:
        flash("启动命令未配置。", "error")
        return redirect(url_for("home"))

    terminal_key = tool["launch_terminal"]
    if terminal_key not in {key for key, _ in terminal_choices()}:
        flash("不支持的终端类型。", "error")
        return redirect(url_for("home"))

    path_value = tool.get("launch_path", "").strip()
    if not path_value:
        flash("启动路径未配置。", "error")
        return redirect(url_for("home"))
    path = expand_path(path_value)
    if not path.exists() or not path.is_dir():
        flash("启动路径不存在。", "error")
        return redirect(url_for("home"))

    try:
        launch_tool(terminal_key, path, command)
    except Exception as exc:
        flash(f"启动失败：{exc}", "error")
    else:
        flash(f"已在 {path} 启动 {tool['name']}", "success")
    return redirect(url_for("home"))


@app.route("/browse")
def browse():
    """目录选择器（复用同一模板）。"""
    path_arg = request.args.get("path")
    context = build_picker_context(path_arg, "dir")
    return render_template("browse_file.html", **context)


@app.route("/browse-file")
def browse_file():
    """文件/目录选择器。"""
    path_arg = request.args.get("path")
    mode = normalize_picker_mode(request.args.get("mode", "file"))
    context = build_picker_context(path_arg, mode)
    return render_template("browse_file.html", **context)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("APP_DEBUG", "1") == "1"
    frozen = is_frozen()

    if frozen:
        # 打包环境下关闭调试，并避免 stdout 写入导致崩溃
        debug = False
        configure_frozen_runtime()
        host = "127.0.0.1"
        port = find_available_port(port, host=host)
        start_server_in_background(host, port)
        wait_for_server(host, port)
        url = f"http://{host}:{port}"
        try:
            import webview  # type: ignore

            webview.create_window(APP_NAME, url, width=1100, height=760)
            webview.start()
        except Exception:
            # WebView 异常时回退到浏览器启动
            import webbrowser

            webbrowser.open(url)
            time.sleep(1)
        sys.exit(0)

    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
