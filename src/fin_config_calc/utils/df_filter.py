import json
from collections.abc import Mapping

import polars as pl
from loguru import logger

_COMPARISON_OPERATORS = {
    "eq": lambda column, value: column == value,
    "ne": lambda column, value: column != value,
    "gt": lambda column, value: column > value,
    "ge": lambda column, value: column >= value,
    "lt": lambda column, value: column < value,
    "le": lambda column, value: column <= value,
}


def _condition_expression(column_name: str, operator: str, value: object) -> pl.Expr:
    column = pl.col(column_name)
    if operator in _COMPARISON_OPERATORS:
        if value is None and operator in {"eq", "ne"}:
            return column.is_null() if operator == "eq" else column.is_not_null()
        return _COMPARISON_OPERATORS[operator](column, value)
    if operator in {"in", "not_in"}:
        if not isinstance(value, list):
            raise ValueError(f"操作符 {operator!r} 的值必须是列表")
        expression = column.is_in(value)
        return expression if operator == "in" else ~expression
    if operator in {"contains", "starts_with", "ends_with"}:
        if not isinstance(value, str):
            raise ValueError(f"操作符 {operator!r} 的值必须是字符串")
        string_column = column.cast(pl.String)
        if operator == "contains":
            return string_column.str.contains(value, literal=True)
        if operator == "starts_with":
            return string_column.str.starts_with(value)
        return string_column.str.ends_with(value)
    if operator in {"is_null", "is_not_null"}:
        if not isinstance(value, bool):
            raise ValueError(f"操作符 {operator!r} 的值必须是布尔值")
        expression = column.is_null() if operator == "is_null" else column.is_not_null()
        return expression if value else ~expression
    raise ValueError(f"不支持的筛选操作符: {operator!r}")


def filter_by_conditions(
    df: pl.DataFrame,
    conditions: Mapping[str, object] | str,
) -> pl.DataFrame:
    """按 dict 或 JSON 中配置的字段条件筛选 Polars DataFrame。

    输入数据：
        df: 待筛选的数据表。
        conditions: 字段到条件的映射或等价 JSON 字符串。标量条件表示等值匹配；
            字典条件支持 ``eq``、``ne``、``gt``、``ge``、``lt``、``le``、
            ``in``、``not_in``、``contains``、``starts_with``、``ends_with``、
            ``is_null`` 和 ``is_not_null``。所有字段及操作符按 AND 组合。
    输出结果：
        满足全部条件的新 DataFrame，保留原始行顺序。

    示例：
        ``filter_by_conditions(df, {"amount": {"ge": 100}, "region": ["华东"]})``
        中列表是等值匹配；集合匹配应写为 ``{"region": {"in": ["华东"]}}``。
    """
    if isinstance(conditions, str):
        try:
            parsed_conditions = json.loads(conditions)
        except json.JSONDecodeError as error:
            raise ValueError("筛选条件不是有效的 JSON") from error
        if not isinstance(parsed_conditions, dict):
            raise TypeError("JSON 筛选条件必须是对象")
        conditions = parsed_conditions

    missing_columns = sorted(set(conditions) - set(df.columns))
    if missing_columns:
        raise ValueError(f"筛选字段不存在: {missing_columns}")
    if not conditions:
        result = df.clone()
        logger.info("条件筛选完成：未配置筛选条件，保留全部 {} 行。", result.height)
        return result

    expressions: list[pl.Expr] = []
    for column_name, configured_condition in conditions.items():
        if isinstance(configured_condition, Mapping):
            if not configured_condition:
                raise ValueError(f"字段 {column_name!r} 的筛选条件不能为空")
            expressions.extend(
                _condition_expression(column_name, str(operator), value)
                for operator, value in configured_condition.items()
            )
        else:
            expressions.append(_condition_expression(column_name, "eq", configured_condition))

    result = df.filter(pl.all_horizontal(expressions))
    logger.info(
        "条件筛选完成：字段={}，输入 {} 行，输出 {} 行。",
        list(conditions),
        df.height,
        result.height,
    )
    return result


def filter_out_na_and_empty(
    df: pl.DataFrame,
    subset: list[str] | None = None,
    mode: str = "any",
) -> pl.DataFrame:
    """
    - 功能：
        - 从 DataFrame 中剔除在指定列上为 NaN 或空字符串的行，支持 "any"/"all" 两种模式。
    - 输入数据：
        - df (pl.DataFrame): 原始数据表；
        - subset (list[str]): 需要检查的列名列表，默认为全部列；
        - mode (str): "any" 表示任一列为空即剔除；"all" 表示全部为空才剔除。
    - 输出结果：
        - pl.DataFrame: 过滤后的新 DataFrame，保留原始行顺序。
    - 副作用：
        - 无，就地不修改原 df。
    - 依赖的其他函数：
        - Polars 横向布尔表达式。
    - 使用场景：
        - 清洗维表或事实表时删除“空记录”，避免后续 join/汇总时受到脏数据影响。
    - 示例：
     >>> df = pl.DataFrame({'A': ['1', '2', None], 'B': ['', 'hello', 'world'], 'C': [4, 5, 6]})
    >>> filter_out_na_and_empty(df, subset=['A','B'], mode='any')
     shape: (1, 3)
     ┌─────┬───────┬─────┐
     │ A   ┆ B     ┆ C   │
     │ --- ┆ ---   ┆ --- │
     │ str ┆ str   ┆ i64 │
     ╞═════╪═══════╪═════╡
     │ 2   ┆ hello ┆ 5   │
     └─────┴───────┴─────┘

    说明：示例中第 2 行（索引 2）因 A 为 NaN 被删除；第 0 行因 B 为空字符串被删除。
    """
    if mode not in {"any", "all"}:
        raise ValueError("mode应为'any'或'all'")

    selected_columns = subset or df.columns

    empty_expressions = []
    for column in selected_columns:
        expression = pl.col(column)
        is_empty = expression.is_null() | (expression.cast(pl.String).str.strip_chars() == "")
        if df.schema[column].is_float():
            is_empty = is_empty | expression.is_nan()
        empty_expressions.append(is_empty.fill_null(False))

    is_empty_row = (
        pl.any_horizontal(empty_expressions)
        if mode == "any"
        else pl.all_horizontal(empty_expressions)
    )
    result = df.filter(~is_empty_row)
    logger.info(
        "空值筛选完成：字段={}，模式={}，输入 {} 行，输出 {} 行。",
        selected_columns,
        mode,
        df.height,
        result.height,
    )
    return result
