from collections.abc import Sequence

import polars as pl


def cast_numeric_columns(
    dataframe: pl.DataFrame,
    columns: Sequence[str],
    table_name: str,
) -> pl.DataFrame:
    """将指定列转换为 Float64，空值按零处理并拒绝非法或非有限值。"""
    missing = sorted(set(columns) - set(dataframe.columns))
    if missing:
        raise ValueError(f"{table_name}缺少字段: {missing}")

    result = dataframe
    for column in columns:
        values = result.get_column(column)
        if values.dtype == pl.String:
            values = values.str.strip_chars()
            values = values.set(values == "", None)

        converted = values.cast(pl.Float64, strict=False)
        invalid_values = values.filter(values.is_not_null() & converted.is_null()).unique().head(10)
        if len(invalid_values):
            raise ValueError(
                f"{table_name}字段[{column}]包含无法转换为数值的值：{invalid_values.to_list()}"
            )

        non_finite_values = (
            converted.filter(converted.is_not_null() & ~converted.is_finite()).unique().head(10)
        )
        if len(non_finite_values):
            raise ValueError(
                f"{table_name}字段[{column}]包含非有限数值：{non_finite_values.to_list()}"
            )

        result = result.with_columns(converted.fill_null(0).alias(column))

    return result
