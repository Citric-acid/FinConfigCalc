from pathlib import Path

from fin_config_calc.utils.df_mapping_1t import mapping_1t as apply_mapping_1t
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def mapping_1t(
    input_file_path: str | Path,
    config_file_path: str | Path,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
    config_sheet_name: str | None = None,
) -> Path:
    """读取数据和单表映射配置，执行映射并输出保留行。

    Args:
        input_file_path: 待处理的 Excel 或 Parquet 文件路径。
        config_file_path: Excel 或 Parquet 格式的单表映射配置路径。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: 输入 Excel 工作表名称；Parquet 文件省略此参数。
        config_sheet_name: 配置 Excel 工作表名称；Parquet 文件省略此参数。

    Returns:
        输出结果的 Path 对象。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    mapping_dataframe = read_dataframe(config_file_path, config_sheet_name)
    result = apply_mapping_1t(dataframe, mapping_dataframe, miss_ok=False)
    return write_dataframe(result, output_file_path)
