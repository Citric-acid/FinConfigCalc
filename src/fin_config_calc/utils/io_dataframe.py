from pathlib import Path

import polars as pl
from loguru import logger

from fin_config_calc.utils.io_dataframe_excel import read_excel, write_excel

EXCEL_INPUT_SUFFIXES = {".xlsx", ".xlsm"}
SUPPORTED_OUTPUT_SUFFIXES = {".xlsx", ".parquet"}


def read_dataframe(
    file_path: str | Path,
    sheet_name: str | None = None,
) -> pl.DataFrame:
    """根据文件扩展名读取 Excel 或 Parquet 数据。

    输入数据：
        file_path: 待读取的文件路径，支持 ``.xlsx``、``.xlsm`` 和 ``.parquet``。
        sheet_name: Excel 工作表名称；Parquet 文件不支持此参数。

    输出结果：
        文件内容对应的 Polars DataFrame。

    使用限制：
        Parquet 文件没有工作表概念，读取时 ``sheet_name`` 必须为 ``None``。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in EXCEL_INPUT_SUFFIXES:
        dataframe = read_excel(path, sheet_name)
        logger.info(
            "读取数据文件完成：路径={}，工作表={}，共 {} 行、{} 列。",
            path,
            sheet_name or "默认工作表",
            dataframe.height,
            dataframe.width,
        )
        return dataframe
    if suffix == ".parquet":
        if sheet_name is not None:
            raise ValueError("Parquet 文件不支持 sheet_name")
        if not path.is_file():
            raise FileNotFoundError(f"Parquet 文件不存在：{path}")
        dataframe = pl.read_parquet(path)
        logger.info(
            "读取数据文件完成：路径={}，共 {} 行、{} 列。",
            path,
            dataframe.height,
            dataframe.width,
        )
        return dataframe

    raise ValueError(f"不支持的输入文件格式：{suffix or '无扩展名'}")


def write_dataframe(
    dataframe: pl.DataFrame,
    file_path: str | Path,
    sheet_name: str = "Sheet1",
) -> Path:
    """根据文件扩展名将 Polars DataFrame 写入 Excel 或 Parquet。

    输入数据：
        dataframe: 待写出的 Polars DataFrame。
        file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        sheet_name: Excel 输出工作表名称；写入 Parquet 时忽略。

    输出结果：
        实际写入文件的 Path 对象。

    副作用：
        自动创建输出文件的父目录，并覆盖已存在的同名文件。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_OUTPUT_SUFFIXES:
        raise ValueError(f"不支持的输出文件格式：{suffix or '无扩展名'}")

    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".xlsx":
        output_path = write_excel(dataframe, path, sheet_name)
        logger.info(
            "写入数据文件完成：路径={}，工作表={}，共 {} 行、{} 列。",
            output_path,
            sheet_name,
            dataframe.height,
            dataframe.width,
        )
        return output_path

    dataframe.write_parquet(path)
    logger.info(
        "写入数据文件完成：路径={}，共 {} 行、{} 列。",
        path,
        dataframe.height,
        dataframe.width,
    )
    return path
