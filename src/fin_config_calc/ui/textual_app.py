from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from collections.abc import Mapping
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from loguru import logger
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, ProgressBar, RichLog, Static
from textual.worker import Worker, WorkerState

from fin_config_calc.utils import (
    ExecutionProgress,
    FunctionPreview,
    execute_functions,
    preview_functions,
)
from fin_config_calc.utils.io_dataframe_excel import read_excel

SETTINGS_PATH = Path(os.getenv("LOCALAPPDATA", Path.home())) / "FinConfigCalc" / "ui-settings.json"
USER_GUIDE_PATH = Path(__file__).with_name("user_guide.html")

_LOG_LEVEL_STYLES = {
    "INFO": "",
    "WARNING": "bold yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}
_LOG_DETAIL_INDENT = " " * 20
_PROGRESS_FUNCTION_WIDTH = 36

try:
    _APP_VERSION = version("fin-config-calc")
except PackageNotFoundError:
    _APP_VERSION = "开发版"


class ScheduleApp(App[None]):
    """运行 Excel 调度表的终端用户界面。

    功能：允许用户输入调度表路径和工作表名称，在后台执行调度任务，并展示结果。
    输入数据：``.xlsx`` 或 ``.xlsm`` 调度表路径，以及可选的工作表名称。
    输出结果：界面中显示执行状态、每一步返回值或异常信息。
    """

    TITLE = "FinConfigCalc"
    SUB_TITLE = "管报任务调度控制台"
    CSS = """
    Screen {
        background: $surface;
    }

    #content {
        width: 1fr;
        height: 1fr;
        background: $panel;
    }

    #title {
        height: 2;
        margin: 1 2 0 2;
        color: $text;
        text-style: bold;
        border-bottom: solid $primary;
    }

    #fields {
        height: 5;
        margin: 1 2 0 2;
    }

    .field-group {
        width: 1fr;
        height: 5;
    }

    #path-group {
        margin-right: 1;
    }

    #sheet-group {
        margin-left: 1;
    }

    .field-label {
        height: 1;
        text-style: bold;
    }

    .field-group Input {
        width: 1fr;
        margin-top: 1;
    }

    #actions {
        height: 3;
        margin: 1 2;
        align-horizontal: right;
    }

    Button {
        min-width: 12;
        margin-left: 1;
    }

    .section-title {
        height: 1;
        color: $text-muted;
        text-style: bold;
    }

    #status {
        height: 2;
        margin: 0 2;
        padding-top: 1;
    }

    #progress {
        width: 1fr;
        height: 2;
        margin: 0 2;
    }

    #progress > #bar {
        width: 1fr;
    }

    #progress .bar--bar {
        color: $primary;
        background: $primary-background;
    }

    #progress .bar--complete {
        color: $success;
    }

    #log-heading {
        margin: 1 2 0 2;
    }

    #output, #preview-table {
        height: 1fr;
        margin: 0 2 1 2;
        border: round $primary-background;
    }

    #output {
        padding: 1;
    }

    #preview-table {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        """创建调度路径、工作表、执行按钮和结果日志控件。"""
        with Vertical(id="content"):
            yield Static(f"管报任务调度控制台  v{_APP_VERSION}", id="title")
            with Horizontal(id="fields"):
                with Vertical(classes="field-group", id="path-group"):
                    yield Label("调度表路径", classes="field-label")
                    yield Input(
                        placeholder=r"D:\Data\损益管报参数.xlsx",
                        id="schedule-path",
                    )
                with Vertical(classes="field-group", id="sheet-group"):
                    yield Label("调度表名称", classes="field-label")
                    yield Input(value="调度", id="sheet-name")
            with Horizontal(id="actions"):
                yield Button("退出", id="quit")
                yield Button("使用说明", id="help")
                yield Button("复制日志", id="copy-log", disabled=True)
                yield Button("预览任务步骤", id="preview")
                yield Button("执行调度", id="run", variant="primary")
            yield Static("等待执行", id="status")
            yield ProgressBar(
                total=1,
                show_percentage=False,
                show_eta=False,
                id="progress",
            )
            yield Static("任务信息", classes="section-title", id="log-heading")
            yield RichLog(id="output", markup=True, wrap=True)
            yield DataTable(id="preview-table", cursor_type="none", zebra_stripes=True)

    def on_mount(self) -> None:
        """初始化任务预览表格列。"""
        self._log_entries: list[str] = []
        self._step_started_at: dict[int, float] = {}
        self._app_thread_id = threading.get_ident()
        try:
            logger.remove(0)
        except ValueError:
            pass
        self._loguru_sink_id = logger.add(
            self._receive_loguru_message,
            level="INFO",
            format="{message}",
        )
        self.query_one("#preview-table", DataTable).add_columns("order", "function", "comments")
        settings = _load_settings()
        self.query_one("#schedule-path", Input).value = settings.get("schedule_path", "")
        self.query_one("#sheet-name", Input).value = settings.get("sheet_name", "调度")

    def on_unmount(self) -> None:
        """移除当前界面的 Loguru sink，避免日志发往已关闭的控件。"""
        logger.remove(self._loguru_sink_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """响应执行和退出按钮。"""
        if event.button.id == "quit":
            self.exit()
            return
        if event.button.id == "help":
            self._open_user_guide()
            return
        if event.button.id == "copy-log":
            self.copy_to_clipboard("\n".join(self._log_entries))
            self.notify("日志已复制")
            return
        if event.button.id not in {"preview", "run"}:
            return

        schedule_path = self.query_one("#schedule-path", Input).value.strip()
        if not schedule_path:
            self._show_error(ValueError("请输入调度表路径"))
            return

        sheet_name = self.query_one("#sheet-name", Input).value.strip() or "调度"
        _save_settings(schedule_path, sheet_name)
        self._set_actions_disabled(True)
        is_preview = event.button.id == "preview"
        self.query_one("#status", Static).update(
            "正在读取任务步骤" if is_preview else "正在读取调度表"
        )
        self.query_one("#progress", ProgressBar).update(total=1, progress=0)
        output = self.query_one("#output", RichLog)
        output.clear()
        self._log_entries.clear()
        self._step_started_at.clear()
        self.query_one("#copy-log", Button).disabled = True
        path = Path(schedule_path).expanduser()
        if is_preview:
            preview_table = self.query_one("#preview-table", DataTable)
            preview_table.clear()
            preview_table.display = True
            output.display = False
            self._preview_schedule(path, sheet_name)
        else:
            self.query_one("#preview-table", DataTable).display = False
            output.display = True
            self._write_log(
                _format_ui_log(
                    "INFO",
                    "调度任务",
                    f"调度表：{schedule_path}\n工作表：{sheet_name}",
                )
            )
            self._execute_schedule(path, sheet_name)

    @work(thread=True, exclusive=True, group="schedule", exit_on_error=False)
    def _preview_schedule(self, schedule_path: Path, sheet_name: str) -> None:
        schedule = read_excel(schedule_path, sheet_name=sheet_name)
        previews = preview_functions(schedule)
        self.call_from_thread(self._show_previews, previews)

    @work(thread=True, exclusive=True, group="schedule", exit_on_error=False)
    def _execute_schedule(self, schedule_path: Path, sheet_name: str) -> None:
        schedule = read_excel(schedule_path, sheet_name=sheet_name)
        execute_functions(schedule, on_progress=self._report_progress)
        self.call_from_thread(self._show_results)

    def _report_progress(self, progress: ExecutionProgress) -> None:
        self.call_from_thread(self._show_progress, progress)

    def _show_progress(self, progress: ExecutionProgress) -> None:
        status = self.query_one("#status", Static)
        progress_bar = self.query_one("#progress", ProgressBar)
        progress_bar.update(total=max(progress.total, 1))
        if progress.state == "started":
            status.update(f"第 {progress.current}/{progress.total} 步：{progress.function}")
            progress_bar.update(progress=progress.current - 1)
            self._step_started_at[progress.current] = time.perf_counter()
            step = f"[{progress.current:02d}/{progress.total:02d}]"
            function = f"{progress.function:<{_PROGRESS_FUNCTION_WIDTH}}"
            comments = f"  {progress.comments}" if progress.comments else ""
            self._write_log(
                _format_ui_log(
                    "START",
                    f"{step} {function}{comments}",
                    style="bold cyan",
                )
            )
            return

        progress_bar.update(progress=progress.current)
        started_at = self._step_started_at.pop(progress.current, None)
        elapsed = time.perf_counter() - started_at if started_at is not None else None
        elapsed_text = f"  耗时 {elapsed:.2f} 秒" if elapsed is not None else ""
        step = f"[{progress.current:02d}/{progress.total:02d}]"
        function = f"{progress.function:<{_PROGRESS_FUNCTION_WIDTH}}"
        self._write_log(
            _format_ui_log(
                "DONE",
                f"{step} {function}{elapsed_text}  输出 {progress.result!s}",
                style="green",
            )
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state is WorkerState.ERROR:
            error = event.worker.error
            if error is not None:
                self._show_error(error)

    def _show_previews(self, previews: list[FunctionPreview]) -> None:
        preview_table = self.query_one("#preview-table", DataTable)
        for preview in previews:
            preview_table.add_row(preview.order, preview.function, preview.comments)
        self.query_one("#status", Static).update(f"预览完成，共 {len(previews)} 步")
        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=max(len(previews), 1), progress=len(previews))
        self._set_actions_disabled(False)

    def _show_results(self) -> None:
        self.query_one("#status", Static).update("执行完成")
        progress = self.query_one("#progress", ProgressBar)
        progress.update(progress=progress.total or 1)
        self._set_actions_disabled(False)

    def _show_error(self, error: BaseException) -> None:
        self.query_one("#preview-table", DataTable).display = False
        output = self.query_one("#output", RichLog)
        output.display = True
        self._write_log(
            _format_ui_log(
                "ERROR",
                "调度任务执行失败",
                _format_error_details(error),
                "bold red",
            )
        )
        self.query_one("#status", Static).update("执行失败")
        self._set_actions_disabled(False)

    def _write_log(self, message: str | Text) -> None:
        text = Text.from_markup(message) if isinstance(message, str) else message
        self.query_one("#output", RichLog).write(text)
        self._log_entries.append(text.plain)
        self.query_one("#copy-log", Button).disabled = False

    def _receive_loguru_message(self, message: Any) -> None:
        text = _format_loguru_record(message.record)
        if threading.get_ident() == self._app_thread_id:
            self.call_later(self._write_log, text)
            return
        try:
            self.call_from_thread(self._write_log, text)
        except RuntimeError:
            pass

    def _set_actions_disabled(self, disabled: bool) -> None:
        self.query_one("#preview", Button).disabled = disabled
        self.query_one("#run", Button).disabled = disabled

    def _open_user_guide(self) -> None:
        if not USER_GUIDE_PATH.is_file():
            self.notify("未找到使用说明文件", severity="error")
            return
        try:
            opened = webbrowser.open(USER_GUIDE_PATH.as_uri())
        except webbrowser.Error:
            opened = False
        if not opened:
            self.notify("无法使用默认浏览器打开使用说明", severity="error")


def main() -> None:
    """启动 FinConfigCalc Textual 用户界面。"""
    if _relaunch_in_windows_terminal():
        return
    ScheduleApp().run()


def _relaunch_in_windows_terminal() -> bool:
    """将 Windows 打包版交给 Windows Terminal，以获得更好的字体渲染。"""
    if (
        sys.platform != "win32"
        or not getattr(sys, "frozen", False)
        or os.getenv("WT_SESSION")
        or os.getenv("FIN_CONFIG_CALC_TERMINAL_RELAUNCHED")
    ):
        return False

    terminal = shutil.which("wt.exe")
    if terminal is None:
        return False

    environment = os.environ.copy()
    environment["FIN_CONFIG_CALC_TERMINAL_RELAUNCHED"] = "1"
    try:
        subprocess.Popen(
            [
                terminal,
                "--window",
                "new",
                "new-tab",
                "--title",
                "FinConfigCalc",
                sys.executable,
            ],
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False
    return True


def _format_error_details(error: BaseException) -> str:
    error_summary = f"{type(error).__name__}: {error}"
    if error.__traceback__ is None:
        return f"执行失败：{error_summary}"

    frames = traceback.extract_tb(error.__traceback__)
    origin = frames[-1]
    location = f"{origin.filename}:{origin.lineno}（函数 {origin.name}）"
    source = f"\n错误代码：{origin.line}" if origin.line else ""
    call_stack = "".join(traceback.format_exception(error)).rstrip()
    return f"执行失败：{error_summary}\n错误位置：{location}{source}\n\n完整调用栈：\n{call_stack}"


def _format_loguru_record(record: Mapping[str, Any]) -> Text:
    """将 Loguru record 转换为具有级别和来源层次的 Rich 文本。"""
    timestamp = record.get("time")
    level_name = str(getattr(record.get("level"), "name", "INFO")).upper()
    message = str(record.get("message", ""))
    style = _LOG_LEVEL_STYLES.get(level_name, "bold red")
    if level_name == "INFO":
        return _format_ui_log(level_name, message, style=style, timestamp=timestamp)

    source = (
        f"{record.get('name', '<unknown>')}:"
        f"{record.get('function', '<unknown>')}:"
        f"{record.get('line', '?')}"
    )
    return _format_ui_log(
        level_name,
        source,
        message,
        style,
        timestamp,
    )


def _format_ui_log(
    category: str,
    source: str,
    detail: str | None = None,
    style: str = "",
    timestamp: datetime | None = None,
) -> Text:
    """按统一的时间、类型、来源和详情结构生成界面日志。"""
    time_text = (timestamp or datetime.now().astimezone()).strftime("%H:%M:%S")

    text = Text()
    text.append(time_text, style="dim")
    text.append("  ")
    text.append(f"{category:<8}  {source}", style=style)
    if detail is None:
        return text

    detail_lines = str(detail).splitlines() or [""]
    for line in detail_lines:
        text.append("\n")
        text.append(_LOG_DETAIL_INDENT, style="dim")
        text.append(line, style=style)
    return text


def _load_settings() -> dict[str, str]:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str)
    }


def _save_settings(schedule_path: str, sheet_name: str) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(
                {"schedule_path": schedule_path, "sheet_name": sheet_name},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
