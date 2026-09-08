import polars as pl
from loguru import logger

from .df_mapping_n import MAPPING_N


def rename_columns(df: pl.DataFrame, rename_dict: dict[str, str]) -> pl.DataFrame:
    """重命名列；目标列已存在时保留被重命名列的值。"""
    for old_name, new_name in rename_dict.items():
        if new_name in df.columns:
            df = df.drop(new_name)
        if old_name in df.columns:
            df = df.rename({old_name: new_name})
    return df


def split_mapping_table(
    df: pl.DataFrame,
    prefix_output: str,
) -> tuple[list[pl.DataFrame], list[list[str]]]:
    """将单张配置映射表拆为可由 ``MAPPING_N`` 执行的多张映射表。"""

    text_columns = [column for column, dtype in df.schema.items() if dtype == pl.String]
    df = df.with_columns(pl.col(text_columns).replace("", None)) if text_columns else df
    non_empty_columns = [
        column for column in df.columns if df.select(pl.col(column).is_not_null().any()).item()
    ]
    df = df.select(non_empty_columns)

    required_columns = ["order_execution", "priority", "mapping_code", "keep_row"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"缺少必要字段: {', '.join(missing_columns)}")
    for column in ["order_execution", "priority"]:
        if df.get_column(column).null_count() or not df.schema[column].is_numeric():
            raise ValueError(f"{column} 必须是数值类型，且非空")
    if (
        df.get_column("mapping_code").null_count()
        or df.get_column("mapping_code").is_duplicated().any()
    ):
        raise ValueError("mapping_code 必须非空，且唯一")

    source_field_columns = [column for column in df.columns if column.startswith("source_field_")]
    source_code_columns = [column for column in df.columns if column.startswith("source_code_")]
    output_field_columns = [column for column in df.columns if column.startswith("output_field_")]
    output_code_columns = [column for column in df.columns if column.startswith("output_code_")]
    _validate_mapping_layout(
        df,
        source_field_columns,
        source_code_columns,
        output_field_columns,
        output_code_columns,
    )

    df = df.with_columns(
        [
            pl.when(pl.col(column).is_not_null())
            .then(pl.concat_str([pl.lit(prefix_output), pl.col(column).cast(pl.Utf8)]))
            .otherwise(None)
            .alias(column)
            for column in output_field_columns
        ]
    )

    result_tables: list[pl.DataFrame] = []
    result_output_fields: list[list[str]] = []
    for sub_df in df.sort("order_execution", maintain_order=True).partition_by(
        "order_execution", maintain_order=True
    ):
        sub_df = sub_df.with_columns(
            rule_dimension=(
                pl.concat_str(
                    [pl.col(column).cast(pl.Utf8) for column in source_field_columns],
                    separator="+",
                    ignore_nulls=True,
                )
                if source_field_columns
                else pl.lit("")
            ).alias("rule_dimension")
        )
        output_fields: list[str] = []
        for field_column in [*source_field_columns, *output_field_columns]:
            code_column = field_column.replace("source_field_", "source_code_").replace(
                "output_field_", "output_code_"
            )
            if field_column not in sub_df.columns or code_column not in sub_df.columns:
                continue
            if field_column.startswith("output_field_"):
                output_fields.extend(
                    sub_df.get_column(field_column)
                    .drop_nulls()
                    .unique(maintain_order=True)
                    .to_list()
                )
            index_columns = [
                column for column in sub_df.columns if column not in {field_column, code_column}
            ]
            sub_df = sub_df.pivot(
                on=field_column,
                index=index_columns,
                values=code_column,
                aggregate_function="first",
            )
            non_empty_columns = [
                column
                for column in sub_df.columns
                if sub_df.select(pl.col(column).is_not_null().any()).item()
            ]
            sub_df = sub_df.select(non_empty_columns)

        validation = MAPPING_N(
            pl.DataFrame(),
            sub_df.rename(
                {
                    "rule_dimension": "映射规则类型",
                    "priority": "映射优先顺序",
                    "mapping_code": "映射规则编码",
                }
            ),
            [],
            validate_only=True,
        )
        if not validation.validate_ok:
            raise ValueError(validation.validate_text_msg)
        result_tables.append(sub_df)
        result_output_fields.append(output_fields)

    logger.info(
        "映射表拆分完成：输入 {} 行，生成 {} 个执行批次。",
        df.height,
        len(result_tables),
    )
    return result_tables, result_output_fields


def _validate_mapping_layout(
    df: pl.DataFrame,
    source_field_columns: list[str],
    source_code_columns: list[str],
    output_field_columns: list[str],
    output_code_columns: list[str],
) -> None:
    """校验同一映射优先级的条件列与值列不冲突。"""
    for group in df.partition_by(["order_execution", "priority"], maintain_order=True):
        if group.select(source_field_columns).unique().height > 1:
            raise ValueError(
                "同一个['order_execution', 'priority']组合下，source_field_XX的组合方式必须是唯一的。"
            )
        if source_code_columns and (
            group.select(source_code_columns)
            .select(pl.struct(source_code_columns).is_duplicated().any())
            .item()
        ):
            raise ValueError(
                "同一个['order_execution', 'priority']组合下，source_code_XX的组合不能有重复。"
            )
    for group in df.partition_by("order_execution", maintain_order=True):
        if group.select(output_field_columns).unique().height > 1:
            raise ValueError("同一个['order_execution']下，output_field_XX的组合方式必须是唯一的。")


def mapping_1t(
    df: pl.DataFrame,
    mapping_table: pl.DataFrame,
    miss_ok: bool = True,
) -> pl.DataFrame:
    """按执行顺序应用单表映射配置，并返回保留行。"""
    input_height = df.height
    map_tables, output_fields = split_mapping_table(
        mapping_table,
        prefix_output="qwer123_",
    )
    for map_df, map_output_fields in zip(map_tables, output_fields, strict=True):
        map_df = map_df.rename(
            {
                "rule_dimension": "映射规则类型",
                "priority": "映射优先顺序",
                "mapping_code": "映射规则编码",
            }
        )
        need_fields = ["keep_row", *map_output_fields]
        df = MAPPING_N(
            input_df=df,
            mapping_df=map_df,
            need_fields=need_fields,
            drop_if_exists=True,
        ).mapping_all(miss_ok=miss_ok)
        df = rename_columns(
            df,
            {
                column: column.replace("qwer123_", "")
                for column in df.columns
                if "qwer123_" in column
            },
        ).filter(pl.col("keep_row") == "是")
    logger.info(
        "单表映射完成：执行 {} 个批次，输入 {} 行，输出 {} 行。",
        len(map_tables),
        input_height,
        df.height,
    )
    return df
