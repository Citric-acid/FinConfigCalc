from pathlib import Path

from fin_config_calc.utils.df_mapping_1t import mapping_1t_with_missed
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

    使用限制：任一批次存在未命中规则的行时，不生成结果文件，而是将未命中行
    （含 ``miss_order_execution`` 批次标记）写入与输出文件同目录的
    ``<文件名>_未命中.xlsx``，随后抛出 ``ValueError`` 中断处理。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    mapping_dataframe = read_dataframe(config_file_path, config_sheet_name)
    result, missed = mapping_1t_with_missed(dataframe, mapping_dataframe)
    if not missed.is_empty():
        output_path = Path(output_file_path)
        missed_path = write_dataframe(
            missed, output_path.with_name(f"{output_path.stem}_未命中.xlsx")
        )
        raise ValueError(f"单表映射存在 {missed.height} 行未命中规则，明细已输出至：{missed_path}")
    return write_dataframe(result, output_file_path)
