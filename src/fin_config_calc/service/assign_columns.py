from pathlib import Path
from typing import Any

from fin_config_calc.utils.df_assign_columns import assign_columns as apply_assign_columns
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def assign_columns(
    input_file_path: str | Path,
    column_values: dict[str, Any],
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
) -> Path:
    """读取表格数据，为多列赋予统一值后保存为新文件。

    Args:
        input_file_path: 待处理的 Excel 或 Parquet 文件路径。
        column_values: 列名与写入值的映射；已存在的同名列会被覆盖。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: Excel 工作表名称；Parquet 文件省略此参数。

    Returns:
        输出结果的 Path 对象。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    result = apply_assign_columns(dataframe, column_values)
    return write_dataframe(result, output_file_path)
