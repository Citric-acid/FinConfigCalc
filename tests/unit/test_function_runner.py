from fin_config_calc.utils.function_runner import (
    ExecutionProgress,
    FunctionPreview,
    execute_functions,
    preview_functions,
)


def test_execute_functions_reports_each_step() -> None:
    progress_events: list[ExecutionProgress] = []

    schedule = [
        {
            "order": 2,
            "function": lambda: "second",
            "params": None,
            "enabled": "Y",
        },
        {
            "order": 1,
            "function": lambda: "first",
            "params": None,
            "enabled": "Y",
            "comments": "第一步说明",
        },
    ]

    results = execute_functions(schedule, on_progress=progress_events.append)

    assert results == ["first", "second"]
    assert progress_events == [
        ExecutionProgress(1, 2, "<lambda>", "started", comments="第一步说明"),
        ExecutionProgress(1, 2, "<lambda>", "completed", "first", "第一步说明"),
        ExecutionProgress(2, 2, "<lambda>", "started"),
        ExecutionProgress(2, 2, "<lambda>", "completed", "second"),
    ]


def test_execute_functions_accepts_callable_without_name_when_progress_is_disabled() -> None:
    class CallableStep:
        def __call__(self) -> str:
            return "completed"

    schedule = [
        {
            "order": 1,
            "function": CallableStep(),
            "params": None,
            "enabled": "Y",
        }
    ]

    assert execute_functions(schedule) == ["completed"]


def test_preview_functions_validates_and_returns_enabled_steps_without_execution() -> None:
    was_called = False

    def task() -> None:
        nonlocal was_called
        was_called = True

    schedule = [
        {"order": 2, "function": task, "params": None, "enabled": "Y", "comments": "导出"},
        {
            "order": 1,
            "function": "service.unpivot.unpivot",
            "params": {},
            "enabled": "Y",
            "comments": "转换月份列",
        },
        {"order": 3, "function": task, "params": None, "enabled": "N", "comments": "跳过"},
    ]

    assert preview_functions(schedule) == [
        FunctionPreview(1, "service.unpivot.unpivot", "转换月份列"),
        FunctionPreview(2, "task", "导出"),
    ]
    assert not was_called
