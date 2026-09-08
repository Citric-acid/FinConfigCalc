from pathlib import Path

import polars as pl
import pytest
from openpyxl import load_workbook

from fin_config_calc.utils.df_diff import (
    diff_by_group,
    diff_by_row,
    diff_by_row_pivot_to_excel,
)


def test_diff_by_row_maps_columns_normalizes_empty_values_and_removes_all_duplicates() -> None:
    first = pl.DataFrame(
        {
            "id": [1, 2, 3, 3, 5],
            "value": ["same", None, "duplicate", "duplicate", "old"],
            "ignored": [1, 2, 3, 3, 4],
        }
    )
    second = pl.DataFrame(
        {
            "key": [1, 2, 4, 5],
            "value": ["same", "", "new", "changed"],
            "ignored": [9, 9, 9, 9],
        }
    )

    result = diff_by_row(
        first,
        second,
        exclude_columns=["ignored"],
        column_map={"id": "key"},
    )

    assert result.select("key", "value", "_tmp_diff_src").to_dicts() == [
        {"key": "5", "value": "old", "_tmp_diff_src": "df_1"},
        {"key": "4", "value": "new", "_tmp_diff_src": "df_2"},
        {"key": "5", "value": "changed", "_tmp_diff_src": "df_2"},
    ]


def test_diff_by_row_supports_nested_values() -> None:
    first = pl.DataFrame({"id": [1, 2], "values": [[1, 2], [3]]})
    second = pl.DataFrame({"id": [1, 2], "values": [[1, 2], [4]]})

    result = diff_by_row(first, second)

    assert result.select("id", "_tmp_diff_src").rows() == [("2", "df_1"), ("2", "df_2")]


def test_diff_by_group_uses_corresponding_columns_and_filters_by_delta() -> None:
    left = pl.DataFrame({"group": ["A", "A", "B", "D"], "amount": [4, 6, 5, 1]})
    right = pl.DataFrame({"key": ["A", "C", "D"], "value": [9.6, 2, 0.6]})

    result = diff_by_group(
        left,
        ["group"],
        ["amount"],
        right,
        right_groupby=["key"],
        right_sum=["value"],
        abs_delta=0.5,
    )

    assert result.sort("group").to_dicts() == [
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


def test_diff_by_group_rejects_mismatched_column_counts() -> None:
    dataframe = pl.DataFrame({"group": ["A"], "amount": [1]})

    with pytest.raises(ValueError, match="left_sum 和 right_sum 的长度不一致"):
        diff_by_group(
            dataframe,
            ["group"],
            ["amount"],
            dataframe,
            right_sum=["amount", "other"],
        )


def test_diff_by_row_pivot_to_excel_counts_and_highlights_changes(tmp_path: Path) -> None:
    differences = pl.DataFrame(
        {
            "id": ["A", "A", "B", "C"],
            "value": ["old", "new", None, "added"],
            "unchanged": ["same", "same", "deleted", None],
            "_tmp_diff_src": ["df_1", "df_2", "df_1", "df_2"],
        }
    )

    result = diff_by_row_pivot_to_excel(
        differences,
        ["id"],
        save_path=tmp_path / "result.xlsx",
    )

    assert result == tmp_path / "result(增1_删1_改1).xlsx"
    workbook = load_workbook(result)
    worksheet = workbook["差异明细"]
    assert worksheet.freeze_panes == "B2"
    assert worksheet.auto_filter.ref == "A1:F4"
    assert [cell.value for cell in worksheet[1]] == [
        "差异类型",
        "id",
        "旧_value",
        "旧_unchanged",
        "新_value",
        "新_unchanged",
    ]
    assert [cell.value for cell in worksheet[2]] == ["改", "A", "old", "same", "new", "same"]
    assert worksheet["C2"].fill.fill_type == "solid"
    assert worksheet["E2"].fill.fill_type == "solid"
    assert worksheet["D2"].fill.fill_type is None
    assert worksheet["F2"].fill.fill_type is None
    workbook.close()
