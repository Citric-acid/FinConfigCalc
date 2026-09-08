from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from importlib import import_module
from numbers import Real
from typing import Any, Literal, NamedTuple

from loguru import logger

PACKAGE_ROOT = "fin_config_calc"
SEQUENCE_COLUMN = "order"
FUNCTION_COLUMN = "function"
PARAMS_COLUMN = "params"
EXECUTE_COLUMN = "enabled"
COMMENTS_COLUMN = "comments"
REQUIRED_COLUMNS = frozenset({SEQUENCE_COLUMN, FUNCTION_COLUMN, PARAMS_COLUMN, EXECUTE_COLUMN})


class ExecutionProgress(NamedTuple):
    """描述调度执行过程中单个步骤的状态。"""

    current: int
    total: int
    function: str
    state: Literal["started", "completed"]
    result: Any = None
    comments: str = ""


class FunctionPreview(NamedTuple):
    """描述调度预览中的单个可执行步骤。"""

    order: int | float
    function: str
    comments: str


def execute_function(
    target: str | Callable[..., Any], params: Mapping[str, Any] | None = None
) -> Any:
    """通过函数名和参数字典执行包内函数。"""
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise TypeError("params 必须是映射类型，例如 dict")

    function = _resolve_function(target) if isinstance(target, str) else target
    if not callable(function):
        raise TypeError("target 必须是函数路径字符串或可调用对象")

    return function(**dict(params))


def execute_functions(
    dataframe: Any,
    on_progress: Callable[[ExecutionProgress], None] | None = None,
) -> list[Any]:
    """校验并按配置表批量执行函数，返回每一步的执行结果。

    配置表必须包含“order”“function”“params”“enabled”列。order 必须为唯一数值；
    enabled 仅允许 ``Y``、``N`` 或空值。标记为 ``Y`` 的行必须提供非空函数名，
    且参数必须是字典、空值或表示 JSON 对象的字符串。传入 ``on_progress`` 时，
    每一步执行前后分别同步发送 ``started`` 和 ``completed`` 事件。
    """
    runnable_rows = _get_runnable_rows(dataframe)

    results = []
    total = len(runnable_rows)
    for current, row in enumerate(runnable_rows, start=1):
        function_name = row[FUNCTION_COLUMN]
        comments = "" if row.get(COMMENTS_COLUMN) is None else str(row[COMMENTS_COLUMN])
        progress_function: str | None = None
        if on_progress is not None:
            if isinstance(function_name, str):
                progress_function = function_name
            else:
                callable_name = getattr(function_name, "__name__", None)
                progress_function = (
                    callable_name
                    if isinstance(callable_name, str)
                    else type(function_name).__name__
                )
            on_progress(
                ExecutionProgress(
                    current,
                    total,
                    progress_function,
                    "started",
                    comments=comments,
                )
            )
        result = execute_function(function_name, _parse_params(row.get(PARAMS_COLUMN)))
        results.append(result)
        if on_progress is not None and progress_function is not None:
            on_progress(
                ExecutionProgress(
                    current,
                    total,
                    progress_function,
                    "completed",
                    result,
                    comments,
                )
            )
    logger.info("调度执行完成：成功执行 {} 个任务。", total)
    return results


def preview_functions(dataframe: Any) -> list[FunctionPreview]:
    """校验调度表并返回按顺序排列的可执行任务，不调用任务函数。

    输入数据：包含 ``order``、``function``、``params`` 和 ``enabled`` 列的
    DataFrame 或行字典列表；可选的 ``comments`` 列用于展示任务说明。
    输出结果：仅包含 ``enabled=Y`` 的任务预览，按 ``order`` 升序排列。
    """
    previews = []
    for row in _get_runnable_rows(dataframe):
        function_name = row[FUNCTION_COLUMN]
        if isinstance(function_name, str):
            display_name = function_name
        else:
            callable_name = getattr(function_name, "__name__", None)
            display_name = (
                callable_name if isinstance(callable_name, str) else type(function_name).__name__
            )
        comments = row.get(COMMENTS_COLUMN)
        previews.append(
            FunctionPreview(
                order=row[SEQUENCE_COLUMN],
                function=display_name,
                comments="" if comments is None else str(comments),
            )
        )
    return previews


def _get_runnable_rows(dataframe: Any) -> list[Mapping[str, Any]]:
    rows = _to_rows(dataframe)
    _validate_schedule(rows, dataframe)
    runnable_rows = [row for row in rows if str(row[EXECUTE_COLUMN]).strip().upper() == "Y"]
    runnable_rows.sort(key=lambda row: row[SEQUENCE_COLUMN])
    return runnable_rows


def _validate_schedule(rows: list[Mapping[str, Any]], dataframe: Any) -> None:
    """在执行前验证调度表的结构、顺序和可执行行参数。

    Args:
        rows: 由 dataframe 转换而来的行字典列表。
        dataframe: 原始 DataFrame 或行字典列表；若具有 columns 属性，
            则校验其包含所有调度必填列。

    Raises:
        ValueError: 当缺少必填列、序号重复、enabled 值不合法，或可执行行的
            function、params 配置不合法时。
        TypeError: 当 order 不是数值时。
    """
    column_names = getattr(dataframe, "columns", None)
    if column_names is not None:
        missing_columns = REQUIRED_COLUMNS - set(column_names)
        if missing_columns:
            raise ValueError(f"调度表缺少必填列：{sorted(missing_columns)}")

    sequence_values: set[Real] = set()
    for row_number, row in enumerate(rows, start=2):
        missing_columns = REQUIRED_COLUMNS - row.keys()
        if missing_columns:
            raise ValueError(f"调度表第 {row_number} 行缺少必填列：{sorted(missing_columns)}")

        sequence = row[SEQUENCE_COLUMN]
        if isinstance(sequence, bool) or not isinstance(sequence, Real):
            raise TypeError(f"调度表第 {row_number} 行的 [{SEQUENCE_COLUMN}] 必须是数值")
        if sequence in sequence_values:
            raise ValueError(f"调度表 [{SEQUENCE_COLUMN}] 列存在重复值：{sequence}")
        sequence_values.add(sequence)

        execute_flag = row[EXECUTE_COLUMN]
        normalized_flag = "" if execute_flag is None else str(execute_flag).strip().upper()
        if normalized_flag not in {"", "Y", "N"}:
            raise ValueError(f"调度表第 {row_number} 行的 [{EXECUTE_COLUMN}] 只能是 Y、N 或空值")
        if normalized_flag != "Y":
            continue

        function_name = row[FUNCTION_COLUMN]
        if not callable(function_name) and (
            not isinstance(function_name, str) or not function_name.strip()
        ):
            raise ValueError(
                f"调度表第 {row_number} 行的 [{FUNCTION_COLUMN}] 必须是非空函数路径或可调用对象"
            )
        try:
            _parse_params(row[PARAMS_COLUMN])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"调度表第 {row_number} 行的 [{PARAMS_COLUMN}] 必须是 JSON 对象字符串或字典：{exc}"
            ) from exc


def _to_rows(dataframe: Any) -> list[Mapping[str, Any]]:
    """将 DataFrame 或类似对象转换为行字典列表。

    支持多种数据源格式：Polars DataFrame、pandas DataFrame 或行字典列表。

    Args:
        dataframe: 数据源对象，可以是 DataFrame 或行字典列表。

    Returns:
        行字典列表，每个元素是包含列名和值的字典。

    Raises:
        TypeError: 当 dataframe 不是支持的格式时。
    """
    if hasattr(dataframe, "iter_rows"):
        return list(dataframe.iter_rows(named=True))
    if hasattr(dataframe, "to_dict"):
        records = dataframe.to_dict("records")
        if isinstance(records, list):
            return records
    if isinstance(dataframe, Iterable) and not isinstance(dataframe, (str, bytes, Mapping)):
        rows = list(dataframe)
        if all(isinstance(row, Mapping) for row in rows):
            return rows
    raise TypeError("dataframe 必须是 DataFrame 或行字典列表")


def _parse_params(value: Any) -> Mapping[str, Any]:
    """解析参数值为字典。

    支持多种参数格式：None（返回空字典）、字典、JSON 字符串。

    Args:
        value: 参数值，可以是 None、dict 或 JSON 字符串。

    Returns:
        参数字典。

    Raises:
        TypeError: 当参数格式不支持或 JSON 解析失败时。
    """
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        if not value.strip():
            return {}
        params = json.loads(value)
        if isinstance(params, Mapping):
            return params
    raise TypeError("参数 必须是 dict 或 JSON 对象字符串")


def _resolve_function(target: str) -> Callable[..., Any]:
    """根据函数路径字符串解析并返回函数对象。

    支持相对路径（相对于包）和绝对路径。若不提供完整包路径，
    默认假定模块在 fin_config_calc 包内。

    Args:
        target: 函数路径，格式为 'module.function' 或 'package.module.function'。

    Returns:
        可调用的函数对象。

    Raises:
        ValueError: 当 target 格式不正确时。
        ImportError: 当模块无法导入时。
        AttributeError: 当模块中找不到函数时。
        TypeError: 当目标不是可调用对象时。
    """
    if not target or "." not in target:
        raise ValueError("target 必须是函数路径，例如 service.unpivot")

    module_name, function_name = target.rsplit(".", 1)
    if module_name == PACKAGE_ROOT or module_name.startswith(f"{PACKAGE_ROOT}."):
        full_module_name = module_name
    else:
        full_module_name = f"{PACKAGE_ROOT}.{module_name}"

    module = import_module(full_module_name)
    function = getattr(module, function_name)
    if not callable(function):
        raise TypeError(f"target 指向的对象不可调用：{target}")
    return function
