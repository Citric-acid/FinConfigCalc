from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from loguru import logger
from textual.containers import Vertical
from textual.widgets import Button, DataTable, Input, ProgressBar, RichLog, Static

from fin_config_calc.ui.textual_app import (
    _APP_VERSION,
    ScheduleApp,
    _format_error_details,
    _relaunch_in_windows_terminal,
)
from fin_config_calc.utils import ExecutionProgress, FunctionPreview


@pytest.fixture(autouse=True)
def use_temporary_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.SETTINGS_PATH",
        tmp_path / "ui-settings.json",
    )


def test_schedule_app_executes_selected_schedule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schedule_path = tmp_path / "schedule.xlsx"
    schedule = object()
    calls: list[object] = []

    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.read_excel",
        lambda path, sheet_name: calls.append((path, sheet_name)) or schedule,
    )

    def execute_with_progress(dataframe: object, on_progress: object) -> list[str]:
        calls.append(dataframe)
        assert callable(on_progress)
        on_progress(ExecutionProgress(1, 2, "service.first", "started", comments="第一步说明"))
        on_progress(
            ExecutionProgress(1, 2, "service.first", "completed", "first.xlsx", "第一步说明")
        )
        on_progress(ExecutionProgress(2, 2, "service.second_with_longer_name", "started"))
        on_progress(
            ExecutionProgress(
                2,
                2,
                "service.second_with_longer_name",
                "completed",
                "second.parquet",
            )
        )
        return ["first.xlsx", "second.parquet"]

    monkeypatch.setattr("fin_config_calc.ui.textual_app.execute_functions", execute_with_progress)

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            title = app.query_one("#title", Static)
            assert str(title.content) == f"管报任务调度控制台  v{_APP_VERSION}"
            assert title.region.height > 0
            app.query_one("#schedule-path", Input).value = str(schedule_path)
            await pilot.click("#run")
            await app.workers.wait_for_complete()

            assert str(app.query_one("#status", Static).content) == "执行完成"
            progress = app.query_one("#progress", ProgressBar)
            assert progress.total == 2
            assert progress.progress == 2
            assert not app.query_one("#run", Button).disabled
            log_text = "\n".join(app._log_entries)
            assert re.search(r"\d{2}:\d{2}:\d{2}  START     \[01/02\] service\.first", log_text)
            start_line = next(line for line in app._log_entries if "  START     [01/02]" in line)
            done_line = next(line for line in app._log_entries if "  DONE      [01/02]" in line)
            assert start_line.index("第一步说明") == done_line.index("耗时")
            assert re.search(
                r"\d{2}:\d{2}:\d{2}  DONE      \[01/02\] service\.first\s+"
                r"耗时 \d+\.\d{2} 秒  输出 first\.xlsx",
                log_text,
            )
            assert re.search(r"\d{2}:\d{2}:\d{2}  INFO      调度任务", log_text)
            assert "SESSION" not in log_text
            assert "SUMMARY" not in log_text
            done_lines = [line for line in app._log_entries if "  DONE      " in line]
            assert len(done_lines) == 2
            assert len({line.index("耗时") for line in done_lines}) == 1

    asyncio.run(run_app())

    assert calls == [(schedule_path, "调度"), schedule]


@pytest.mark.parametrize("terminal_size", [(80, 24), (180, 50)])
def test_schedule_app_content_adapts_to_terminal_size(terminal_size: tuple[int, int]) -> None:
    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test(size=terminal_size):
            content = app.query_one("#content", Vertical)
            output = app.query_one("#output", RichLog)
            progress = app.query_one("#progress", ProgressBar)

            assert content.region.width == terminal_size[0]
            assert content.region.height == terminal_size[1]
            assert output.region.width == terminal_size[0] - 4
            assert output.region.height > 0
            assert progress.region.width == output.region.width
            assert app.query_one("#bar").region.width == progress.region.width

    asyncio.run(run_app())


def test_packaged_app_relaunches_in_windows_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    launches: list[tuple[list[str], dict[str, str], int]] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"D:\Apps\FinConfigCalc.exe")
    monkeypatch.delenv("WT_SESSION", raising=False)
    monkeypatch.delenv("FIN_CONFIG_CALC_TERMINAL_RELAUNCHED", raising=False)
    monkeypatch.setattr("fin_config_calc.ui.textual_app.shutil.which", lambda name: r"C:\wt.exe")
    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.subprocess.Popen",
        lambda command, env, creationflags: launches.append((command, env, creationflags)),
    )

    assert _relaunch_in_windows_terminal()
    assert launches[0][0] == [
        r"C:\wt.exe",
        "--window",
        "new",
        "new-tab",
        "--title",
        "FinConfigCalc",
        r"D:\Apps\FinConfigCalc.exe",
    ]
    assert launches[0][1]["FIN_CONFIG_CALC_TERMINAL_RELAUNCHED"] == "1"
    assert launches[0][2] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_app_does_not_relaunch_from_windows_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("WT_SESSION", "session-id")

    assert not _relaunch_in_windows_terminal()


def test_schedule_app_previews_steps_without_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schedule_path = tmp_path / "schedule.xlsx"
    schedule = object()
    calls: list[object] = []

    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.read_excel",
        lambda path, sheet_name: calls.append((path, sheet_name)) or schedule,
    )
    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.preview_functions",
        lambda dataframe: (
            calls.append(dataframe) or [FunctionPreview(1, "service.unpivot.unpivot", "转换月份列")]
        ),
    )
    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.execute_functions",
        lambda *args, **kwargs: pytest.fail("预览不应执行任务"),
    )

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            app.query_one("#schedule-path", Input).value = str(schedule_path)
            await pilot.click("#preview")
            await app.workers.wait_for_complete()

            assert str(app.query_one("#status", Static).content) == "预览完成，共 1 步"
            preview_table = app.query_one("#preview-table", DataTable)
            assert preview_table.display
            assert preview_table.row_count == 1
            assert preview_table.get_row_at(0) == [
                1,
                "service.unpivot.unpivot",
                "转换月份列",
            ]
            assert not app.query_one("#output", RichLog).display
            assert not app.query_one("#preview", Button).disabled
            assert not app.query_one("#run", Button).disabled

    asyncio.run(run_app())

    assert calls == [(schedule_path, "调度"), schedule]


def test_schedule_app_requires_schedule_path() -> None:
    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            await pilot.click("#run")

            assert str(app.query_one("#status", Static).content) == "执行失败"

    asyncio.run(run_app())


def test_schedule_app_opens_user_guide(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    guide_path = tmp_path / "user_guide.html"
    guide_path.write_text("<html></html>", encoding="utf-8")
    opened_urls: list[str] = []
    monkeypatch.setattr("fin_config_calc.ui.textual_app.USER_GUIDE_PATH", guide_path)
    monkeypatch.setattr(
        "fin_config_calc.ui.textual_app.webbrowser.open",
        lambda url: opened_urls.append(url) or True,
    )

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            await pilot.click("#help")

    asyncio.run(run_app())

    assert opened_urls == [guide_path.as_uri()]


def test_schedule_app_copies_plain_text_log(monkeypatch: pytest.MonkeyPatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        ScheduleApp,
        "copy_to_clipboard",
        lambda self, text: copied.append(text),
    )

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            await pilot.click("#run")
            copy_button = app.query_one("#copy-log", Button)
            assert not copy_button.disabled

            await pilot.click("#copy-log")

    asyncio.run(run_app())

    assert len(copied) == 1
    assert re.fullmatch(
        r"\d{2}:\d{2}:\d{2}  ERROR     调度任务执行失败\n"
        r"                    执行失败：ValueError: 请输入调度表路径",
        copied[0],
    )


def test_schedule_app_shows_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_read_error(path: Path, sheet_name: str) -> object:
        raise FileNotFoundError(path)

    monkeypatch.setattr("fin_config_calc.ui.textual_app.read_excel", raise_read_error)

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            app.query_one("#schedule-path", Input).value = "missing.xlsx"
            await pilot.click("#run")
            await app.workers.wait_for_complete()

            assert str(app.query_one("#status", Static).content) == "执行失败"
            assert not app.query_one("#run", Button).disabled

    asyncio.run(run_app())


def test_schedule_app_displays_info_and_higher_loguru_messages(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("fin_config_calc.ui.textual_app.read_excel", lambda *args, **kwargs: [])

    def execute_with_logs(*args: object, **kwargs: object) -> list[object]:
        logger.debug("不应显示")
        logger.info("读取完成")
        logger.warning("数据需要检查")
        logger.error("第一行\n第二行")
        return []

    monkeypatch.setattr("fin_config_calc.ui.textual_app.execute_functions", execute_with_logs)

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            app.query_one("#schedule-path", Input).value = "schedule.xlsx"
            await pilot.click("#run")
            await app.workers.wait_for_complete()
            await pilot.pause()

            log_text = "\n".join(app._log_entries)
            assert "不应显示" not in log_text
            assert re.search(r"\d{2}:\d{2}:\d{2}  INFO      读取完成", log_text)
            assert "INFO      test_textual_app:execute_with_logs:" not in log_text
            assert "WARNING   test_textual_app:execute_with_logs:" in log_text
            assert "ERROR     test_textual_app:execute_with_logs:" in log_text
            assert "数据需要检查" in log_text
            assert "第一行\n                    第二行" in log_text

    asyncio.run(run_app())

    assert "读取完成" not in capsys.readouterr().err


def test_format_error_details_includes_source_location_and_traceback() -> None:
    def raise_nested_error() -> None:
        raise RuntimeError("测试错误")

    try:
        raise_nested_error()
    except RuntimeError as error:
        details = _format_error_details(error)

    assert "执行失败：RuntimeError: 测试错误" in details
    assert f"{__file__}:" in details
    assert "（函数 raise_nested_error）" in details
    assert '错误代码：raise RuntimeError("测试错误")' in details
    assert "完整调用栈：\nTraceback (most recent call last):" in details


def test_schedule_app_restores_and_saves_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings_path = tmp_path / "ui-settings.json"
    settings_path.write_text(
        json.dumps({"schedule_path": "previous.xlsx", "sheet_name": "上次调度"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("fin_config_calc.ui.textual_app.SETTINGS_PATH", settings_path)
    monkeypatch.setattr("fin_config_calc.ui.textual_app.read_excel", lambda *args, **kwargs: [])
    monkeypatch.setattr("fin_config_calc.ui.textual_app.preview_functions", lambda dataframe: [])

    async def run_app() -> None:
        app = ScheduleApp()
        async with app.run_test() as pilot:
            assert app.query_one("#schedule-path", Input).value == "previous.xlsx"
            assert app.query_one("#sheet-name", Input).value == "上次调度"

            app.query_one("#schedule-path", Input).value = "next.xlsx"
            app.query_one("#sheet-name", Input).value = "新调度"
            await pilot.click("#preview")
            await app.workers.wait_for_complete()

    asyncio.run(run_app())

    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "schedule_path": "next.xlsx",
        "sheet_name": "新调度",
    }
