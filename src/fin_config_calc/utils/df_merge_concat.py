import json
from collections import defaultdict
from typing import Any

import polars as pl
from loguru import logger


def merge_left(
    df_left: pl.DataFrame,
    df_right: pl.DataFrame,
    left_on: list[str],
    right_on: list[str] | None = None,
    keep_right: list[str] | None = None,
    right_suffix: str = "",
    if_duplicate: str = "raise",
) -> pl.DataFrame:
    """Left join while requiring unique right-hand keys and preserving left row count."""
    right_on = right_on or left_on
    keep_right = keep_right or [column for column in df_right.columns if column not in right_on]

    if len(left_on) != len(right_on):
        raise ValueError("left_on 和 right_on 元素个数必须相等")
    missing_left = set(left_on) - set(df_left.columns)
    if missing_left:
        raise ValueError(f"df_left 中不存在列: {missing_left}")
    missing_right = set(right_on + keep_right) - set(df_right.columns)
    if missing_right:
        raise ValueError(f"df_right 中不存在列: {missing_right}")

    right_df = df_right.select(right_on + keep_right)
    prefixed_right_on = [f"__merge_r__{column}" for column in right_on]
    right_df = right_df.rename(dict(zip(right_on, prefixed_right_on, strict=True)))
    if right_df.filter(pl.struct(prefixed_right_on).is_duplicated()).height:
        raise ValueError(f"右表键值组合 {right_on} 不唯一, 会导致数据翻倍, 请检查!")

    rename_map = {
        column: f"{column}{right_suffix}"
        for column in keep_right
        if column in df_left.columns and right_suffix
    }
    right_df = right_df.rename(rename_map)
    keep_right = [rename_map.get(column, column) for column in keep_right]

    duplicate_columns = (set(df_left.columns) - set(left_on)) & (
        set(right_df.columns) - set(prefixed_right_on)
    )
    replacement_columns: dict[str, str] = {}
    if duplicate_columns:
        if if_duplicate == "keep_left":
            right_df = right_df.drop(list(duplicate_columns))
            keep_right = [column for column in keep_right if column not in duplicate_columns]
        elif if_duplicate == "keep_right":
            df_left = df_left.drop(list(duplicate_columns))
        elif if_duplicate == "keep_right_if_left_isnull":
            replacement_columns = {
                column: f"__merge_r_value__{column}" for column in duplicate_columns
            }
            right_df = right_df.rename(replacement_columns)
        else:
            raise ValueError(f"左表和右表有重复列: {duplicate_columns}")

    merged_df = df_left.join(
        right_df,
        left_on=left_on,
        right_on=prefixed_right_on,
        how="left",
    )
    for column, replacement in replacement_columns.items():
        merged_df = merged_df.with_columns(
            pl.when(pl.col(column).is_null() | (pl.col(column) == ""))
            .then(pl.col(replacement))
            .otherwise(pl.col(column))
            .alias(column)
        ).drop(replacement)

    output_columns = df_left.columns + [
        column for column in keep_right if column not in df_left.columns
    ]
    merged_df = merged_df.select(output_columns)
    if merged_df.height != df_left.height:
        raise ValueError("merge_left 合并后的行数不等于左表行数")
    logger.info(
        "左连接完成：连接字段={}，左表 {} 行，结果 {} 行、{} 列。",
        left_on,
        df_left.height,
        merged_df.height,
        merged_df.width,
    )
    return merged_df


def merge_left_metadata(
    df_left: pl.DataFrame,
    df_metadata: pl.DataFrame,
    relations: dict[str, Any] | str,
) -> pl.DataFrame:
    """按配置一次性关联多个维度的元数据属性。

    输入数据：左表、包含 ``dimension`` 和 ``element_code`` 的拼接元数据表，以及
    以左表字段为键的关联配置。每项配置包含 ``dimension`` 和 ``attributes``；
    ``attributes`` 的键为元数据属性字段，值为输出字段名。配置可传字典或 JSON 字符串。

    输出结果：保留左表行数和原字段，并追加配置的属性字段；输出字段已存在时使用
    元数据关联值覆盖。每个维度内的 ``element_code`` 必须唯一。
    """
    if isinstance(relations, str):
        try:
            relations = json.loads(relations)
        except json.JSONDecodeError as error:
            raise ValueError(f"关联关系不是有效的 JSON: {error.msg}") from error
    if not isinstance(relations, dict) or not relations:
        raise ValueError("关联关系必须是非空对象")

    required_metadata_columns = {"dimension", "element_code"}
    missing_metadata_columns = required_metadata_columns - set(df_metadata.columns)
    if missing_metadata_columns:
        raise ValueError(f"df_metadata 中不存在列: {missing_metadata_columns}")

    result = df_left
    output_columns: set[str] = set()
    for left_column, relation in relations.items():
        if not isinstance(left_column, str) or not left_column:
            raise ValueError("关联关系中的左表字段名必须是非空字符串")
        if not isinstance(relation, dict):
            raise TypeError(f"字段 {left_column} 的关联配置必须是对象")

        dimension = relation.get("dimension")
        attributes = relation.get("attributes")
        if not isinstance(dimension, str) or not dimension:
            raise ValueError(f"字段 {left_column} 的 dimension 必须是非空字符串")
        if not isinstance(attributes, dict) or not attributes:
            raise ValueError(f"字段 {left_column} 的 attributes 必须是非空对象")
        if not all(
            isinstance(source, str) and source and isinstance(target, str) and target
            for source, target in attributes.items()
        ):
            raise ValueError(f"字段 {left_column} 的属性字段名和输出字段名必须是非空字符串")

        duplicate_outputs = output_columns & set(attributes.values())
        if duplicate_outputs:
            raise ValueError(f"属性输出字段重复: {duplicate_outputs}")
        output_columns.update(attributes.values())

        metadata_for_dimension = df_metadata.filter(pl.col("dimension") == dimension).select(
            "element_code", *attributes.keys()
        )
        if metadata_for_dimension.is_empty():
            raise ValueError(f"df_metadata 中不存在维度: {dimension}")
        result = merge_left(
            result,
            metadata_for_dimension.rename(attributes),
            left_on=[left_column],
            right_on=["element_code"],
            keep_right=list(attributes.values()),
            if_duplicate="keep_right",
        )

    logger.info(
        "元数据属性关联完成：关联 {} 个维度字段，输入 {} 行，输出 {} 行、{} 列。",
        len(relations),
        df_left.height,
        result.height,
        result.width,
    )
    return result


def merge_and_concat_dfs_by_pid(
    list_dfs: list[pl.DataFrame],
) -> tuple[bool, pl.DataFrame]:
    """Combine partial DataFrames into a wide table keyed by ``pid``."""
    if not list_dfs:
        result = pl.DataFrame(schema={"pid": pl.Null})
        logger.info("按 pid 横向拼接完成：输入 0 个数据表，输出 0 行。")
        return True, result

    fields_by_name: defaultdict[str, list[pl.DataFrame]] = defaultdict(list)
    for dataframe in list_dfs:
        if "pid" not in dataframe.columns:
            raise ValueError("所有数据表必须包含 pid 列")
        for column in dataframe.columns:
            if column != "pid":
                fields_by_name[column].append(dataframe.select("pid", column))

    if not fields_by_name:
        result = list_dfs[0].select("pid").unique(maintain_order=True)
        logger.info(
            "按 pid 横向拼接完成：输入 {} 个数据表，输出 {} 行、{} 列。",
            len(list_dfs),
            result.height,
            result.width,
        )
        return True, result

    merged_df: pl.DataFrame | None = None
    for column_frames in fields_by_name.values():
        field_df = pl.concat(column_frames, how="vertical_relaxed")
        if merged_df is None:
            merged_df = field_df
        else:
            merged_df = merged_df.join(field_df, on="pid", how="full", coalesce=True)

    assert merged_df is not None
    if merged_df.select(pl.col("pid").is_duplicated().any()).item():
        logger.error("拼接完的结果中，pid列中存在重复")
        return False, merged_df
    logger.info(
        "按 pid 横向拼接完成：输入 {} 个数据表，输出 {} 行、{} 列。",
        len(list_dfs),
        merged_df.height,
        merged_df.width,
    )
    return True, merged_df


def concat_dfs(dataframes: list[pl.DataFrame]) -> pl.DataFrame:
    """按字段并集和输入顺序纵向拼接多个 DataFrame。

    Args:
        dataframes: 待拼接的 DataFrame 列表，至少包含一个 DataFrame。

    Returns:
        拼接后的 DataFrame；输入中缺失的字段使用空值补齐。
    """
    if not dataframes:
        raise ValueError("至少需要一个 DataFrame 才能拼接")

    result = pl.concat(dataframes, how="diagonal_relaxed")
    logger.info(
        "数据表纵向拼接完成：输入 {} 个数据表、共 {} 行，输出 {} 行、{} 列。",
        len(dataframes),
        sum(dataframe.height for dataframe in dataframes),
        result.height,
        result.width,
    )
    return result
