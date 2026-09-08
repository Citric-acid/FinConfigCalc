from pathlib import Path
from typing import Any

from fin_config_calc.utils.df_merge_concat import merge_left_metadata
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def merge_dims_attribute(
    input_file_path: str | Path,
    metadata_file_path: str | Path,
    relations: dict[str, Any] | str,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
    metadata_sheet_name: str | None = None,
) -> Path:
    """读取待关联数据和维度元数据，批量关联属性后输出结果。

    Args:
        input_file_path: 待关联的 Excel 或 Parquet 文件路径。
        metadata_file_path: 维度元数据文件路径，需包含 ``dimension`` 和
            ``element_code`` 字段。
        relations: 以左表字段为键的关联配置，可传字典或 JSON 字符串。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: 输入 Excel 工作表名称；Parquet 文件省略此参数。
        metadata_sheet_name: 元数据 Excel 工作表名称；Parquet 文件省略此参数。

    Returns:
        输出结果的 Path 对象。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    metadata_dataframe = read_dataframe(metadata_file_path, metadata_sheet_name)
    result = merge_left_metadata(dataframe, metadata_dataframe, relations)
    return write_dataframe(result, output_file_path)
