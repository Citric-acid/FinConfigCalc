from collections.abc import Mapping, Sequence
from pathlib import Path

from fin_config_calc.utils.df_diff import (
    diff_by_group as compare_by_group,
)
from fin_config_calc.utils.df_diff import (
    diff_by_row as compare_by_row,
)
from fin_config_calc.utils.df_diff import (
    diff_by_row_pivot_to_excel,
)
from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


def diff_by_row(
    first_file_path: str | Path,
    second_file_path: str | Path,
    output_file_path: str | Path,
    check_columns: Sequence[str] | None = None,
    exclude_columns: Sequence[str] | None = None,
    column_map: Mapping[str, str] | None = None,
    first_sheet_name: str | None = None,
    second_sheet_name: str | None = None,
    output_sheet_name: str = "Sheet1",
    diff_source_col: str = "_tmp_diff_src",
) -> Path:
    """读取两个数据文件，执行行级差异比较并保存结果。

    输入数据：
        first_file_path、second_file_path: 待比较的 Excel 或 Parquet 文件。
        output_file_path: 差异结果路径，支持 ``.xlsx`` 和 ``.parquet``。
        其余参数用于指定比较字段、排除字段、列名映射、工作表和来源字段名。

    输出结果：
        实际写入的输出文件 Path。
    """
    first_dataframe = read_dataframe(first_file_path, first_sheet_name)
    second_dataframe = read_dataframe(second_file_path, second_sheet_name)
    result = compare_by_row(
        first_dataframe,
        second_dataframe,
        check_columns=check_columns,
        exclude_columns=exclude_columns,
        column_map=column_map,
        _tmp_diff_col=diff_source_col,
    )
    return write_dataframe(result, output_file_path, output_sheet_name)


def diff_by_row_to_excel(
    first_file_path: str | Path,
    second_file_path: str | Path,
    output_file_path: str | Path,
    join_keys: Sequence[str],
    check_columns: Sequence[str] | None = None,
    exclude_columns: Sequence[str] | None = None,
    column_map: Mapping[str, str] | None = None,
    first_sheet_name: str | None = None,
    second_sheet_name: str | None = None,
    diff_source_col: str = "_tmp_diff_src",
    output_sheet_name: str = "差异明细",
) -> Path:
    """读取两个数据文件，执行行级比较并输出带高亮的差异 Excel 报表。

    输入数据：
        first_file_path、second_file_path: 待比较的 Excel 或 Parquet 文件。
        output_file_path: ``.xlsx`` 输出路径模板，文件名会附加增删改数量。
        join_keys: 归并新旧记录的关联字段。
        其余参数用于指定比较字段、排除字段、列名映射、工作表及来源字段名。

    输出结果：
        实际生成的、文件名包含增删改统计的 Excel 路径。
    """
    first_dataframe = read_dataframe(first_file_path, first_sheet_name)
    second_dataframe = read_dataframe(second_file_path, second_sheet_name)
    differences = compare_by_row(
        first_dataframe,
        second_dataframe,
        check_columns=check_columns,
        exclude_columns=exclude_columns,
        column_map=column_map,
        _tmp_diff_col=diff_source_col,
    )
    return diff_by_row_pivot_to_excel(
        differences,
        join_keys,
        diff_source_col=diff_source_col,
        save_path=output_file_path,
        sheet_name=output_sheet_name,
    )


def diff_by_group(
    left_file_path: str | Path,
    left_groupby: Sequence[str],
    left_sum: Sequence[str],
    right_file_path: str | Path,
    output_file_path: str | Path,
    right_groupby: Sequence[str] | None = None,
    right_sum: Sequence[str] | None = None,
    keep_groupby: str = "left",
    abs_delta: float = 0.5,
    left_sheet_name: str | None = None,
    right_sheet_name: str | None = None,
    output_sheet_name: str = "Sheet1",
) -> Path:
    """读取两个数据文件，执行分组汇总差异比较并保存结果。

    输入数据：
        left_file_path、right_file_path: 待比较的 Excel 或 Parquet 文件。
        left_groupby、right_groupby: 两侧按位置对应的分组字段。
        left_sum、right_sum: 两侧按位置对应的求和字段。
        output_file_path: 差异结果路径，支持 ``.xlsx`` 和 ``.parquet``。
        其余参数用于指定输出字段命名侧、差异阈值及工作表。

    输出结果：
        实际写入的输出文件 Path。
    """
    left_dataframe = read_dataframe(left_file_path, left_sheet_name)
    right_dataframe = read_dataframe(right_file_path, right_sheet_name)
    result = compare_by_group(
        left_dataframe,
        left_groupby,
        left_sum,
        right_dataframe,
        right_groupby=right_groupby,
        right_sum=right_sum,
        keep_groupby=keep_groupby,
        abs_delta=abs_delta,
    )
    return write_dataframe(result, output_file_path, output_sheet_name)
