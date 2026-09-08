from pathlib import Path

from fin_config_calc.utils.df_standardize_columns import standardize_columns_by_rules
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def standardize_columns(
    input_file_path: str | Path,
    config_file_path: str | Path,
    field_name: str,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
    config_sheet_name: str | None = None,
) -> Path:
    """根据规则表统一数据的列名和字段类型，并输出结果。

    Args:
        input_file_path: 待处理的 Excel 或 Parquet 文件路径。
        config_file_path: Excel 或 Parquet 格式的列标准化规则表路径。
        field_name: 规则表中表示原始列名的字段名。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: 输入 Excel 工作表名称；Parquet 文件省略此参数。
        config_sheet_name: 规则表 Excel 工作表名称；Parquet 文件省略此参数。

    Returns:
        输出结果的 Path 对象。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    rule_dataframe = read_dataframe(config_file_path, config_sheet_name)
    result = standardize_columns_by_rules(dataframe, rule_dataframe, field_name)
    return write_dataframe(result, output_file_path)
