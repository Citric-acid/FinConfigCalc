from pathlib import Path

import polars as pl
from openpyxl import load_workbook

from fin_config_calc.service import diff_by_group, diff_by_row, diff_by_row_to_excel


def test_diff_by_row_reads_compares_and_writes_files(tmp_path: Path) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    output_path = tmp_path / "row_diff.parquet"
    pl.DataFrame({"id": ["A", "B"], "value": [1, 2]}).write_parquet(first_path)
    pl.DataFrame({"id": ["A", "B"], "value": [1, 3]}).write_parquet(second_path)

    result = diff_by_row(first_path, second_path, output_path)

    assert result == output_path
    assert pl.read_parquet(output_path).to_dicts() == [
        {"id": "B", "value": "2", "_tmp_diff_src": "df_1"},
        {"id": "B", "value": "3", "_tmp_diff_src": "df_2"},
    ]


def test_diff_by_row_to_excel_reads_compares_and_writes_styled_report(tmp_path: Path) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    output_path = tmp_path / "report.xlsx"
    pl.DataFrame({"id": ["A", "B"], "value": ["same", "old"]}).write_parquet(first_path)
    pl.DataFrame({"id": ["A", "B"], "value": ["same", "new"]}).write_parquet(second_path)

    result = diff_by_row_to_excel(first_path, second_path, output_path, ["id"])

    assert result == tmp_path / "report(增0_删0_改1).xlsx"
    workbook = load_workbook(result)
    assert [cell.value for cell in workbook["差异明细"][2]] == ["改", "B", "old", "new"]
    workbook.close()


def test_diff_by_group_reads_aggregates_and_writes_files(tmp_path: Path) -> None:
    left_path = tmp_path / "left.parquet"
    right_path = tmp_path / "right.parquet"
    output_path = tmp_path / "group_diff.parquet"
    pl.DataFrame({"group": ["A", "A", "B"], "amount": [4, 6, 5]}).write_parquet(left_path)
    pl.DataFrame({"key": ["A", "C"], "value": [9, 2]}).write_parquet(right_path)

    result = diff_by_group(
        left_path,
        ["group"],
        ["amount"],
        right_path,
        output_path,
        right_groupby=["key"],
        right_sum=["value"],
        abs_delta=1,
    )

    assert result == output_path
    assert pl.read_parquet(output_path).sort("group").to_dicts() == [
        {
            "group": "A",
            "amount_left": 10.0,
            "value_right": 9.0,
            "amount_diff": 1.0,
        },
        {
            "group": "B",
            "amount_left": 5.0,
            "value_right": None,
            "amount_diff": 5.0,
        },
        {
            "group": "C",
            "amount_left": None,
            "value_right": 2.0,
            "amount_diff": -2.0,
        },
    ]
