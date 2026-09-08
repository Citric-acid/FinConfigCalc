from collections.abc import Mapping
from pathlib import Path

from fin_config_calc.utils.df_filter import filter_by_conditions as apply_filter_by_conditions
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def filter_by_conditions(
    input_file_path: str | Path,
    conditions: Mapping[str, object] | str,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
) -> Path:
    """根据配置的字段条件筛选数据并输出结果。

    功能：
        读取 Excel 或 Parquet 数据，调用 Polars 条件筛选工具处理数据，
        再将结果写入指定位置。

    输入数据：
        input_file_path: 待处理的 Excel 或 Parquet 文件路径。
        conditions: 字段筛选条件的映射或等价 JSON 字符串。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_name: Excel 工作表名称；Parquet 文件省略此参数。

    输出结果：
        输出文件的 Path 对象。

    配置格式：
        标量值表示等值匹配；字典值用于指定操作符，例如
        ``{"amount": {"ge": 100}, "region": {"in": ["华东", "华南"]}}``。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    result = apply_filter_by_conditions(dataframe, conditions)
    return write_dataframe(result, output_file_path)
