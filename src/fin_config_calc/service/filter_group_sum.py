from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

from fin_config_calc.utils.df_filter import filter_by_conditions
from fin_config_calc.utils.df_group import group_sum
from fin_config_calc.utils.io_dataframe import read_dataframe
from fin_config_calc.utils.io_dataframe_excel import read_excel, write_excel

FIELD_NAME_COLUMN = "standard"
FIELD_COMMENT_COLUMN = "comments"


class GroupSumParams(TypedDict, total=False):
    """``group_sum`` 支持的分组聚合参数。"""

    sum_by: list[str] | None
    group_by: list[str] | None
    group_by_exclude: list[str] | None
    abs_delta: float


def filter_group_sum_to_excel(
    input_file_path: str | Path,
    output_file_path: str | Path,
    field_mapping_file_path: str | Path | None = None,
    field_mapping_sheet_name: str | None = None,
    conditions: Mapping[str, object] | None = None,
    group_sum_params: GroupSumParams | None = None,
    input_sheet_name: str | None = None,
    output_sheet_name: str = "Sheet1",
) -> Path:
    """筛选并分组聚合数据，附带字段中文说明导出到 Excel。

    功能：
        读取待处理文件，依次调用条件筛选和分组聚合工具，再读取字段对照表，
        将英文列名、对应中文说明及聚合结果写入指定 Excel 工作表。

    输入数据：
        input_file_path、input_sheet_name: 待处理文件路径及 Excel 工作表名称。
        conditions: 传给 ``filter_by_conditions`` 的筛选条件；为 ``None`` 时
            跳过筛选，直接处理全部输入数据。
        group_sum_params: 传给 ``group_sum`` 的参数字典，支持 ``sum_by``、
            ``group_by``、``group_by_exclude`` 和 ``abs_delta``；为 ``None`` 时
            跳过分组聚合，直接导出筛选结果。
        field_mapping_file_path、field_mapping_sheet_name: 字段对照表路径及工作表名称；
            对照表必须包含 ``standard`` 和 ``comments`` 两列；路径为 ``None`` 时
            不添加中文说明行。
        output_file_path、output_sheet_name: 输出 ``.xlsx`` 文件路径及工作表名称。

    输出结果：
        实际写入的 Excel 文件 Path。配置字段对照表时，第一行为英文列名，第二行为
        对应中文说明，第三行起为数据；未配置对照表时，第二行起直接写入数据。
    """
    dataframe = read_dataframe(input_file_path, input_sheet_name)
    filtered = filter_by_conditions(dataframe, conditions) if conditions is not None else dataframe
    result = group_sum(filtered, **group_sum_params) if group_sum_params is not None else filtered

    column_comments = None
    if field_mapping_file_path is not None:
        field_mapping = read_excel(field_mapping_file_path, field_mapping_sheet_name)
        missing_columns = [
            column
            for column in (FIELD_NAME_COLUMN, FIELD_COMMENT_COLUMN)
            if column not in field_mapping.columns
        ]
        if missing_columns:
            raise ValueError(f"字段对照表缺少必需字段: {missing_columns}")

        column_comments = dict(
            zip(
                field_mapping.get_column(FIELD_NAME_COLUMN).cast(str).to_list(),
                field_mapping.get_column(FIELD_COMMENT_COLUMN).cast(str).to_list(),
                strict=True,
            )
        )
    output_path = Path(output_file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return write_excel(result, output_path, output_sheet_name, column_comments)
