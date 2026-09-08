import polars as pl
from loguru import logger


def unpivot_df(
    df: pl.DataFrame,
    unpivot_columns: list[str],
    variable_column: str,
    value_column: str,
) -> pl.DataFrame:
    """将 Polars DataFrame 从宽表逆透视为长表。

    Args:
        df: 待处理的数据框。
        unpivot_columns: 需要逆透视的列名。
        variable_column: 存放原列名的新列名。
        value_column: 存放单元格值的新列名。

    Returns:
        逆透视后的数据框，未包含在 ``unpivot_columns`` 中的列将作为标识列保留。
    """
    index_columns = [column for column in df.columns if column not in unpivot_columns]
    result = df.unpivot(
        on=unpivot_columns,
        index=index_columns,
        variable_name=variable_column,
        value_name=value_column,
    )
    logger.info(
        "逆透视完成：展开字段={}，输入 {} 行，输出 {} 行。",
        unpivot_columns,
        df.height,
        result.height,
    )
    return result
