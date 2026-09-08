from pathlib import Path

from fin_config_calc.utils.df_check import df_check_metadata, df_check_metadata_validity
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def check_metadata(
    input_file_path: str | Path,
    metadata_file_path: str | Path,
    output_file_path: str | Path,
    input_sheet_name: str | None = None,
    metadata_sheet_name: str | None = None,
) -> Path:
    """读取待检测数据和元数据，完成元数据及维度成员校验并输出结果。

    输入数据：待检测文件、元数据文件及输出路径；输入支持 Excel 和 Parquet，
    输出支持 ``.xlsx`` 和 ``.parquet``。

    输出结果：将待检测数据的错误明细写入输出路径；无错误时返回 Path。

    使用限制：元数据自身存在错误时抛出 ``ValueError``，不再校验待检测数据，
    也不会生成输出文件。待检测数据存在错误时，先生成错误明细文件，再抛出
    ``ValueError`` 中断处理。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    metadata_df = read_dataframe(metadata_file_path, metadata_sheet_name)
    metadata_errors = df_check_metadata_validity(metadata_df)
    if not metadata_errors.is_empty():
        error_text = "\n".join(
            f"{row['dimension']}/{row['element_code']}: {row['REASON']}"
            for row in metadata_errors.iter_rows(named=True)
        )
        raise ValueError(f"维度元数据校验失败：\n{error_text}")

    result = df_check_metadata(dataframe, metadata_df)
    output_path = write_dataframe(result, output_file_path)
    if not result.is_empty():
        raise ValueError(f"待检测数据元数据合法性校验失败，错误明细已输出至：{output_path}")
    return output_path
