from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from fin_config_calc.utils.df_assign_columns import assign_columns
from fin_config_calc.utils.df_filter import filter_by_conditions
from fin_config_calc.utils.df_merge_concat import concat_dfs
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def concat(
    input_file_paths: list[str | Path],
    output_file_path: str | Path,
    input_sheet_names: list[str | None] | None = None,
    source_column: str | None = None,
    source_values: list[Any] | None = None,
) -> Path:
    """读取多个表格文件，按需添加数据来源列后纵向拼接并保存。

    Args:
        input_file_paths: 待拼接的 Excel 或 Parquet 文件路径列表。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。
        input_sheet_names: 可选的 Excel 工作表名称列表；省略时自动为所有输入使用
            ``None``。Parquet 对应位置必须为 ``None``。
        source_column: 可选的数据来源列名；指定时需要同时传入 ``source_values``。
        source_values: 各输入文件对应的数据来源值，元素个数必须与输入文件数相等。

    Returns:
        输出结果的 Path 对象。
    """
    resolved_sheet_names = (
        [None] * len(input_file_paths) if input_sheet_names is None else input_sheet_names
    )
    if len(input_file_paths) != len(resolved_sheet_names):
        raise ValueError("input_file_paths 和 input_sheet_names 的元素个数必须相等")
    if (source_column is None) != (source_values is None):
        raise ValueError("source_column 和 source_values 必须同时提供或同时省略")
    if source_values is not None and len(input_file_paths) != len(source_values):
        raise ValueError("input_file_paths 和 source_values 的元素个数必须相等")

    dataframes = []
    for index, (input_file_path, input_sheet_name) in enumerate(
        zip(input_file_paths, resolved_sheet_names, strict=True)
    ):
        dataframe = read_dataframe(input_file_path, input_sheet_name)
        if source_column is not None:
            assert source_values is not None
            dataframe = assign_columns(dataframe, {source_column: source_values[index]})
        dataframes.append(dataframe)
    result = concat_dfs(dataframes)
    return write_dataframe(result, output_file_path)


def append_with_overwrite(
    database_file_path: str | Path,
    upload_file_path: str | Path,
    overwrite_conditions: Mapping[str, object],
    database_sheet_name: str | None = None,
    upload_sheet_name: str | None = None,
) -> Path:
    """按指定条件替换存量文件中的数据分区，并原位追加上传数据。

    输入数据：
        database_file_path: 作为存量数据库的 XLSX 或 Parquet 文件路径，也是输出路径。
        upload_file_path: 待上传的 Excel 或 Parquet 文件路径。
        overwrite_conditions: 要覆盖的数据分区条件。所有条件按 AND 组合，上传文件中的
            每一行都必须满足这些条件，例如
            ``{"dim_period": "202601", "dim_scenario": "ACT"}``。
        database_sheet_name: 存量 Excel 的工作表名称；Parquet 文件省略此参数。
        upload_sheet_name: 上传 Excel 的工作表名称；Parquet 文件省略此参数。

    输出结果：
        原位更新后的存量文件 Path 对象。存量中满足条件的行被上传数据替换，
        其他行保持原有顺序，上传数据追加在末尾；两边字段不同时按字段并集补空值。

    使用限制：
        覆盖条件和上传文件均不能为空。函数会在写入前完成条件校验，避免上传不属于
        指定分区的数据。
    """
    if not overwrite_conditions:
        raise ValueError("overwrite_conditions 不能为空")

    database = read_dataframe(database_file_path, database_sheet_name)
    upload = read_dataframe(upload_file_path, upload_sheet_name)
    if upload.is_empty():
        raise ValueError("上传文件不能为空")

    matching_upload = filter_by_conditions(upload, overwrite_conditions)
    if matching_upload.height != upload.height:
        raise ValueError("上传文件中存在不满足 overwrite_conditions 的数据")

    row_index_column = "__append_with_overwrite_row_index__"
    while row_index_column in database.columns:
        row_index_column = f"_{row_index_column}"

    indexed_database = database.with_row_index(row_index_column)
    matching_database = filter_by_conditions(indexed_database, overwrite_conditions)
    remaining_database = indexed_database.join(
        matching_database.select(row_index_column),
        on=row_index_column,
        how="anti",
    ).drop(row_index_column)

    result = concat_dfs([remaining_database, upload])
    logger.info(
        "数据上传完成：上传前共 {} 行，删除 {} 行，追加 {} 行，上传后共 {} 行。",
        database.height,
        matching_database.height,
        upload.height,
        result.height,
    )
    output_sheet_name = database_sheet_name or "Sheet1"
    return write_dataframe(result, database_file_path, output_sheet_name)
