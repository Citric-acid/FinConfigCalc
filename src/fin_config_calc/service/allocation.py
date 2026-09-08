import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import polars as pl

from fin_config_calc.utils.df_allocator import DataAllocator
from fin_config_calc.utils.df_assign_columns import assign_columns
from fin_config_calc.utils.df_filter import filter_by_conditions
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def _require_columns(dataframe: pl.DataFrame, columns: Sequence[str], table_name: str) -> None:
    missing = sorted(set(columns) - set(dataframe.columns))
    if missing:
        raise ValueError(f"{table_name}缺少字段: {missing}")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def expand_allocation_factors(
    factor_dataframe: pl.DataFrame,
    metadata_dataframe: pl.DataFrame,
    *,
    out_prefix: str = "out_",
    dimension_column: str = "dimension",
    element_column: str = "element_code",
    base_flag_column: str = "is_base",
    parent_column: str = "parent",
    base_flag_value: str = "Y",
) -> pl.DataFrame:
    """将分摊因子 out 维度中的汇总成员扩充为全部基础后代成员。

    输入数据：
        factor_dataframe: 分摊因子长表，待扩充列使用 ``out_维度名`` 格式。
        metadata_dataframe: 维度元数据长表，每行描述成员、父成员及是否基础成员。
        其余参数用于声明元数据列名、out 前缀和基础成员标识。

    输出结果：
        与原因子表列结构一致的 DataFrame。一个汇总成员对应多个基础后代时，
        原行扩充为多行；多个 out 维度需要扩充时形成笛卡尔组合。

    使用限制：
        空值、基础成员及元数据中不存在的特殊编码保持原值。元数据中同一维度的
        成员编码必须唯一，父子关系不能成环。``reg{表达式}`` 使用 ``re.match``
        匹配对应维度的成员编码，并扩充为所有命中成员的基础后代。
    """
    _require_columns(
        metadata_dataframe,
        [dimension_column, element_column, base_flag_column, parent_column],
        "维度元数据表",
    )
    if factor_dataframe.is_empty():
        return factor_dataframe.clone()

    metadata_rows = metadata_dataframe.select(
        [dimension_column, element_column, base_flag_column, parent_column]
    ).iter_rows(named=True)
    members_by_dimension: dict[str, dict[Any, tuple[Any, bool]]] = defaultdict(dict)
    for row in metadata_rows:
        dimension = row[dimension_column]
        element = row[element_column]
        if _is_blank(dimension) or _is_blank(element):
            continue
        dimension_name = str(dimension).strip()
        members = members_by_dimension[dimension_name]
        if element in members:
            raise ValueError(f"维度元数据表 [{dimension_name}] 存在重复成员: {element!r}")
        is_base = str(row[base_flag_column]).strip().upper() == base_flag_value.upper()
        members[element] = (row[parent_column], is_base)

    descendants: dict[tuple[str, Any], list[Any]] = {}
    for dimension, members in members_by_dimension.items():
        children: dict[Any, list[Any]] = defaultdict(list)
        for element, (parent, _) in members.items():
            if not _is_blank(parent):
                children[parent].append(element)

        def get_base_descendants(
            element: Any,
            dimension_name: str,
            dimension_members: dict[Any, tuple[Any, bool]],
            dimension_children: dict[Any, list[Any]],
            path: frozenset[Any] = frozenset(),
        ) -> list[Any]:
            cache_key = (dimension_name, element)
            if cache_key in descendants:
                return descendants[cache_key]
            if element in path:
                raise ValueError(f"维度元数据表 [{dimension_name}] 的父子关系存在环: {element!r}")
            member = dimension_members.get(element)
            if member is None:
                return []
            if member[1]:
                result = [element]
            else:
                result = []
                next_path = path | {element}
                for child in dimension_children.get(element, []):
                    result.extend(
                        get_base_descendants(
                            child,
                            dimension_name,
                            dimension_members,
                            dimension_children,
                            next_path,
                        )
                    )
            descendants[cache_key] = list(dict.fromkeys(result))
            return descendants[cache_key]

        for element in members:
            get_base_descendants(element, dimension, members, children)

    rows = factor_dataframe.to_dicts()
    for column in factor_dataframe.columns:
        if not column.startswith(out_prefix):
            continue
        dimension = column[len(out_prefix) :]
        if dimension not in members_by_dimension:
            continue
        expanded_rows: list[dict[str, Any]] = []
        for row in rows:
            value = row[column]
            if isinstance(value, str) and value.startswith("reg{") and value.endswith("}"):
                pattern = re.compile(value[4:-1])
                replacements = []
                for element in members_by_dimension[dimension]:
                    if pattern.match(str(element)):
                        replacements.extend(descendants[(dimension, element)])
                replacements = list(dict.fromkeys(replacements))
            else:
                replacements = descendants.get((dimension, value), [])
            if not replacements:
                expanded_rows.append(row)
                continue
            for replacement in replacements:
                expanded_rows.append({**row, column: replacement})
        rows = expanded_rows

    return pl.DataFrame(rows, schema=factor_dataframe.schema).unique(maintain_order=True)


def allocation(
    input_file_path: str | Path,
    factor_file_path: str | Path,
    metadata_file_path: str | Path,
    output_file_path: str | Path,
    value_columns: str | Sequence[str],
    input_sheet_name: str | None = None,
    factor_sheet_name: str | None = None,
    metadata_sheet_name: str | None = None,
    output_sheet_name: str = "Sheet1",
    rate_column: str = "rate",
    out_prefix: str = "out_",
    in_prefix: str = "in_",
    dimension_column: str = "dimension",
    element_column: str = "element_code",
    base_flag_column: str = "is_base",
    parent_column: str = "parent",
    base_flag_value: str = "Y",
    keep_label: bool = False,
    group_by: Sequence[str] | None = None,
    group_by_exclude: Sequence[str] | None = None,
    abs_delta: float = 5,
    factor_output_file_path: str | Path | None = None,
    factor_output_sheet_name: str = "Sheet1",
    factor_query: Mapping[str, object] | str | None = None,
    assign_result: dict[str, Any] | None = None,
) -> Path:
    """读取待摊数据、分摊因子和维度元数据，执行分摊并写出结果文件。

    因子表按 out 列的空值组合拆分规则，out 非空列用于匹配待摊数据，in 非空列
    用于覆盖分入维度。每组因子都以完整待摊数据作为输入，其 out 字段值自行定义
    本组分摊范围；范围外数据不进入结果，也不视为异常。提供可选因子输出路径时，
    将筛选并展开后的因子表写入对应文件。``factor_query`` 使用通用 filter 条件格式
    选择本次执行的因子；``assign_result`` 使用通用 assign_columns 格式，为最终
    分摊结果新增或覆盖固定值列。
    """
    input_dataframe = read_dataframe(input_file_path, input_sheet_name)
    factor_dataframe = read_dataframe(factor_file_path, factor_sheet_name)
    metadata_dataframe = read_dataframe(metadata_file_path, metadata_sheet_name)
    if factor_query is not None:
        factor_dataframe = filter_by_conditions(factor_dataframe, factor_query)
    factor_dataframe = expand_allocation_factors(
        factor_dataframe,
        metadata_dataframe,
        out_prefix=out_prefix,
        dimension_column=dimension_column,
        element_column=element_column,
        base_flag_column=base_flag_column,
        parent_column=parent_column,
        base_flag_value=base_flag_value,
    )
    if factor_output_file_path is not None:
        write_dataframe(factor_dataframe, factor_output_file_path, factor_output_sheet_name)
    _require_columns(factor_dataframe, [rate_column], "分摊系数表")

    out_columns = [column for column in factor_dataframe.columns if column.startswith(out_prefix)]
    in_columns = [column for column in factor_dataframe.columns if column.startswith(in_prefix)]
    if not out_columns:
        raise ValueError(f"分摊系数表不存在以 {out_prefix!r} 开头的分出维度字段")
    if not in_columns:
        raise ValueError(f"分摊系数表不存在以 {in_prefix!r} 开头的分入维度字段")

    normalized = factor_dataframe.with_columns(
        pl.when(pl.col(column).cast(pl.String, strict=False).str.strip_chars() == "")
        .then(None)
        .otherwise(pl.col(column))
        .alias(column)
        for column in [*out_columns, *in_columns]
    )
    patterns = (
        normalized.select([pl.col(column).is_not_null().alias(column) for column in out_columns])
        .unique(maintain_order=True)
        .to_dicts()
    )
    results: list[pl.DataFrame] = []
    allocator = DataAllocator()
    for pattern in patterns:
        left_on = [column[len(out_prefix) :] for column in out_columns if pattern[column]]
        right_on = [column for column in out_columns if pattern[column]]
        conditions = [
            pl.col(column).is_not_null() if pattern[column] else pl.col(column).is_null()
            for column in out_columns
        ]
        current_factor = normalized.filter(pl.all_horizontal(conditions))
        replace_mapping = {}
        for column in in_columns:
            non_null_count = current_factor.get_column(column).is_not_null().sum()
            if non_null_count not in {0, current_factor.height}:
                raise ValueError(f"同一出方维度组合内，分入字段 {column!r} 必须全空或全非空")
            if non_null_count == current_factor.height:
                replace_mapping[column] = column[len(in_prefix) :]
        if not replace_mapping:
            raise ValueError("分摊系数表存在没有任何分入维度的规则")
        current_factor = current_factor.rename(replace_mapping)
        result, _ = allocator.allocation_family(
            df_left=input_dataframe,
            df_rate=current_factor,
            value_left=value_columns,
            rate_right=rate_column,
            allocation_list=[
                {
                    "left_on": left_on,
                    "right_on": right_on,
                    "replace_right": list(replace_mapping.values()),
                }
            ],
            keep_label=keep_label,
            group_by=group_by,
            group_by_exclude=group_by_exclude,
            abs_delta=abs_delta,
            miss_ok=True,
        )
        results.append(result)

    if results:
        output = pl.concat(results, how="diagonal_relaxed")
    else:
        output = input_dataframe.head(0)
    if assign_result is not None:
        output = assign_columns(output, assign_result)
    return write_dataframe(output, output_file_path, output_sheet_name)
