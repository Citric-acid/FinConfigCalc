from typing import Any

import polars as pl
from loguru import logger


def assign_columns(dataframe: pl.DataFrame, column_values: dict[str, Any]) -> pl.DataFrame:
    """为 DataFrame 新增或覆盖多列，并将每列设为指定的统一值。

    Args:
        dataframe: 待处理的 Polars DataFrame。
        column_values: 列名与写入值的映射；列名不能为空。

    Returns:
        包含目标列的 DataFrame；已存在的同名列会被覆盖。
    """
    if not isinstance(column_values, dict) or not column_values:
        raise ValueError("列值定义必须是非空字典")
    if any(
        not isinstance(column_name, str) or not column_name.strip() for column_name in column_values
    ):
        raise ValueError("列名必须是非空字符串")

    result = dataframe.with_columns(
        [pl.lit(value).alias(column_name) for column_name, value in column_values.items()]
    )
    logger.info(
        "列赋值完成：字段={}，共 {} 行、{} 列。",
        list(column_values),
        result.height,
        result.width,
    )
    return result
