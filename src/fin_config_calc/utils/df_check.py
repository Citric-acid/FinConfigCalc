from typing import Any

import polars as pl
from loguru import logger

METADATA_COLUMNS = ["dimension", "element_code", "element_name", "is_base", "parent"]
RESULT_SCHEMA = {
    "dimension": pl.Utf8,
    "element_code": pl.Utf8,
    "REASON": pl.Utf8,
}
DATA_CHECK_COLUMNS = ["CHECK_DIMENSION", "CHECK_ELEMENT_CODE", "REASON"]
ROW_INDEX_COLUMN = "__CHECK_ROW_INDEX"


def _check_required_columns(dataframe: pl.DataFrame, required_columns: list[str]) -> None:
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(f"缺少必要字段: {', '.join(missing_columns)}")


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _display(value: Any) -> str | None:
    return None if value is None else str(value)


def _result_frame(results: list[dict[str, str | None]]) -> pl.DataFrame:
    if not results:
        return pl.DataFrame(schema=RESULT_SCHEMA)
    return pl.DataFrame(results, schema=RESULT_SCHEMA)


def _data_check_result_frame(
    dataframe: pl.DataFrame,
    errors: list[tuple[int | None, str, str | None, str]],
) -> pl.DataFrame:
    result_schema = {
        **dataframe.schema,
        "CHECK_DIMENSION": pl.Utf8,
        "CHECK_ELEMENT_CODE": pl.Utf8,
        "REASON": pl.Utf8,
    }
    if not errors:
        return pl.DataFrame(schema=result_schema)

    error_frame = pl.DataFrame(
        {
            ROW_INDEX_COLUMN: [error[0] for error in errors],
            "CHECK_DIMENSION": [error[1] for error in errors],
            "CHECK_ELEMENT_CODE": [error[2] for error in errors],
            "REASON": [error[3] for error in errors],
        },
        schema={
            ROW_INDEX_COLUMN: pl.get_index_type(),
            "CHECK_DIMENSION": pl.Utf8,
            "CHECK_ELEMENT_CODE": pl.Utf8,
            "REASON": pl.Utf8,
        },
    )
    indexed_data = dataframe.with_row_index(ROW_INDEX_COLUMN)
    return error_frame.join(indexed_data, on=ROW_INDEX_COLUMN, how="left").select(
        *dataframe.columns,
        *DATA_CHECK_COLUMNS,
    )


def df_check_metadata_validity(metadata_df: pl.DataFrame) -> pl.DataFrame:
    """检查元数据定义本身是否合法。

    输入数据：包含 ``dimension``、``element_code``、``element_name``、``is_base``
    和 ``parent`` 字段的元数据 DataFrame。

    输出结果：包含 ``dimension``、``element_code`` 和 ``REASON`` 的错误明细；
    无错误时返回同结构的空 DataFrame。
    """
    _check_required_columns(metadata_df, METADATA_COLUMNS)
    results: list[dict[str, str | None]] = []

    duplicate_rows = metadata_df.filter(
        pl.struct(["dimension", "element_code"]).is_duplicated()
    ).unique(["dimension", "element_code"], maintain_order=True)
    for row in duplicate_rows.iter_rows(named=True):
        results.append(
            {
                "dimension": _display(row["dimension"]),
                "element_code": _display(row["element_code"]),
                "REASON": "dimension、element_code 组合不允许重复",
            }
        )

    for row in metadata_df.iter_rows(named=True):
        dimension = row["dimension"]
        element_code = row["element_code"]
        element_name = row["element_name"]
        is_base = row["is_base"]
        parent = row["parent"]
        error_context = {
            "dimension": _display(dimension),
            "element_code": _display(element_code),
        }

        if _is_empty(element_name):
            results.append({**error_context, "REASON": "element_name 不允许为空"})
        if _is_empty(is_base):
            results.append({**error_context, "REASON": "is_base 不允许为空"})
        elif is_base not in {"Y", "N"}:
            results.append({**error_context, "REASON": "is_base 只能是 Y 或 N"})

        if _is_empty(parent):
            continue
        parent_rows = metadata_df.filter(
            (pl.col("dimension") == dimension) & (pl.col("element_code") == parent)
        )
        if parent_rows.is_empty():
            results.append({**error_context, "REASON": "parent 必须存在于同维度的 element_code"})
        elif "N" not in parent_rows.get_column("is_base").to_list():
            results.append({**error_context, "REASON": "parent 对应元素的 is_base 必须为 N"})

    result = _result_frame(results)
    logger.info(
        "元数据定义校验完成：检查 {} 行，发现 {} 项错误。",
        metadata_df.height,
        result.height,
    )
    return result


def df_check_metadata(dataframe: pl.DataFrame, metadata_df: pl.DataFrame) -> pl.DataFrame:
    """使用元数据检查待检测数据中的维度成员是否合法。

    输入数据：待检测 DataFrame，以及包含维度和元素定义的元数据 DataFrame。
    元数据 ``dimension`` 的值即待检测 DataFrame 的维度列名，且只有
    ``is_base=Y`` 的 ``element_code`` 可以出现在待检测数据中。

    输出结果：每条错误保留待检测 DataFrame 的全部原始字段，并追加
    ``CHECK_DIMENSION``、``CHECK_ELEMENT_CODE`` 和 ``REASON``；同一非法成员出现
    在多条原始记录中时逐条输出。无错误时返回同结构的空 DataFrame。不执行
    交叉验证或完整性验证。
    """
    _check_required_columns(metadata_df, METADATA_COLUMNS)
    reserved_columns = [*DATA_CHECK_COLUMNS, ROW_INDEX_COLUMN]
    conflicting_columns = [column for column in reserved_columns if column in dataframe.columns]
    if conflicting_columns:
        raise ValueError(f"待检测数据包含保留字段: {', '.join(conflicting_columns)}")

    errors: list[tuple[int | None, str, str | None, str]] = []
    dimensions = metadata_df.get_column("dimension").unique(maintain_order=True).to_list()

    for dimension in dimensions:
        if _is_empty(dimension):
            continue
        dimension_name = str(dimension)
        if dimension_name not in dataframe.columns:
            errors.append((None, dimension_name, None, "待检测数据缺少维度字段"))
            continue

        valid_elements = set(
            metadata_df.filter((pl.col("dimension") == dimension) & (pl.col("is_base") == "Y"))
            .get_column("element_code")
            .to_list()
        )
        values = dataframe.get_column(dimension_name).to_list()
        for row_index, value in enumerate(values):
            if _is_empty(value):
                reason = "不允许为空值"
            elif isinstance(value, str) and value.startswith(("reg{", "var{")):
                continue
            elif value not in valid_elements:
                reason = "合法性校验失败"
            else:
                continue
            errors.append((row_index, dimension_name, _display(value), reason))

    errors.sort(key=lambda error: -1 if error[0] is None else error[0])
    result = _data_check_result_frame(dataframe, errors)
    logger.info(
        "数据元数据校验完成：检查 {} 行、{} 个维度，发现 {} 项错误。",
        dataframe.height,
        len(dimensions),
        result.height,
    )
    return result
