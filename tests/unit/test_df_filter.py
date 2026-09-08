import math

import polars as pl
import pytest

from fin_config_calc.utils.df_filter import filter_by_conditions, filter_out_na_and_empty


def test_filter_by_conditions_combines_comparison_and_set_conditions() -> None:
    dataframe = pl.DataFrame(
        {
            "region": ["华东", "华南", "华东", "华东"],
            "amount": [50, 150, 300, 600],
        }
    )

    result = filter_by_conditions(
        dataframe,
        {"region": {"in": ["华东"]}, "amount": {"ge": 100, "lt": 500}},
    )

    assert result.to_dicts() == [{"region": "华东", "amount": 300}]


def test_filter_by_conditions_accepts_json_and_string_conditions() -> None:
    dataframe = pl.DataFrame(
        {
            "code": ["FIN-001", "OPS-002", "FIN-003"],
            "status": ["启用", "启用", "停用"],
        }
    )

    result = filter_by_conditions(
        dataframe,
        '{"code": {"starts_with": "FIN-"}, "status": "启用"}',
    )

    assert result.to_dicts() == [{"code": "FIN-001", "status": "启用"}]


def test_filter_by_conditions_supports_null_conditions() -> None:
    dataframe = pl.DataFrame({"code": ["A", None, "B"]})

    result = filter_by_conditions(dataframe, {"code": {"is_null": True}})

    assert result.to_dicts() == [{"code": None}]


@pytest.mark.parametrize(
    ("conditions", "error_type", "message"),
    [
        ({"missing": 1}, ValueError, "筛选字段不存在"),
        ({"value": {"between": [1, 2]}}, ValueError, "不支持的筛选操作符"),
        ({"value": {"in": 1}}, ValueError, "值必须是列表"),
        ("[]", TypeError, "JSON 筛选条件必须是对象"),
    ],
)
def test_filter_by_conditions_rejects_invalid_conditions(
    conditions: dict[str, object] | str,
    error_type: type[Exception],
    message: str,
) -> None:
    dataframe = pl.DataFrame({"value": [1, 2]})

    with pytest.raises(error_type, match=message):
        filter_by_conditions(dataframe, conditions)


def test_filter_out_na_and_empty_any_handles_null_nan_and_whitespace() -> None:
    dataframe = pl.DataFrame(
        {
            "text": ["keep", "", "  ", None, "keep"],
            "amount": [1.0, 2.0, 3.0, 4.0, math.nan],
        }
    )

    result = filter_out_na_and_empty(dataframe, mode="any")

    assert result.to_dicts() == [{"text": "keep", "amount": 1.0}]


def test_filter_out_na_and_empty_all_combines_null_and_empty_values() -> None:
    dataframe = pl.DataFrame(
        {
            "left": [None, None, "value"],
            "right": ["", "value", ""],
        }
    )

    result = filter_out_na_and_empty(dataframe, subset=["left", "right"], mode="all")

    assert result.to_dicts() == [
        {"left": None, "right": "value"},
        {"left": "value", "right": ""},
    ]


def test_filter_out_na_and_empty_rejects_invalid_mode() -> None:
    dataframe = pl.DataFrame({"value": [1]})

    with pytest.raises(ValueError, match="mode应为'any'或'all'"):
        filter_out_na_and_empty(dataframe, mode="invalid")
