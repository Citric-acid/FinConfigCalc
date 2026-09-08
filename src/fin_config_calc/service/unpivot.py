from pathlib import Path

from fin_config_calc.utils.df_reshape import unpivot_df
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe

REQUIRED_CONFIG_KEYS = {"unpivot_columns", "variable_column", "value_column"}


def unpivot(
    input_file_path: str | Path,
    unpivot_columns: list[str],
    variable_column: str,
    value_column: str,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
) -> Path:
    """根据配置对数据执行逆透视并输出结果。

    功能：
        读取两列 key/value 格式的配置表，使用其中的 ``unpivot_columns``、
        ``variable_column`` 和 ``value_column`` 参数对目标数据执行逆透视，
        再将结果写入指定位置。

    输入数据：
        input_file_path: 待处理的 Excel 或 Parquet 文件路径。
        unpivot_columns: 需要逆透视的列名。
        variable_column: 保存原列名的目标列名。
        value_column: 保存原单元格值的目标列名。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: Excel 工作表名称；Parquet 文件省略此参数。

    输出结果：
        输出文件的 Path 对象。

    配置格式：
        ``unpivot_columns`` 的值使用 JSON 数组字符串，例如``["一月", "二月"]``；另外两个配置值使用字符串。
    """

    dataframe = read_dataframe(input_file_path, input_sheet_name)
    result = unpivot_df(dataframe, unpivot_columns, variable_column, value_column)
    return write_dataframe(result, output_file_path)
