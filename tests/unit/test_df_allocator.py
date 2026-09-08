import polars as pl
import pytest

from fin_config_calc.utils.df_allocator import DataAllocator


def test_allocation_basic_normalizes_weights_and_balances_values() -> None:
    source = pl.DataFrame(
        {
            "company": ["A", "B"],
            "description": ["first", "second"],
            "amount": [100, -50],
            "profit": [40, -20],
        }
    )
    rates = pl.DataFrame(
        {
            "entity": ["A", "A", "B", "B"],
            "department": ["X", "Y", "X", "Y"],
            "weight": [1, 3, 2, 2],
        }
    )

    result = DataAllocator().allocation_basic(
        source,
        rates,
        value_left=["amount", "profit"],
        rate_right="weight",
        left_on=["company"],
        right_on=["entity"],
        replace_right=["department"],
        update_column={"status": "allocated"},
        keep_label=True,
    )

    assert result.select(pl.col("amount").sum(), pl.col("profit").sum()).row(0) == (
        0.0,
        0.0,
    )
    assert result.filter(pl.col("dim_alclabel") == "in").select(
        "company", "department", "amount", "profit"
    ).to_dicts() == [
        {"company": "A", "department": "X", "amount": 25.0, "profit": 10.0},
        {"company": "A", "department": "Y", "amount": 75.0, "profit": 30.0},
        {"company": "B", "department": "X", "amount": -25.0, "profit": -10.0},
        {"company": "B", "department": "Y", "amount": -25.0, "profit": -10.0},
    ]
    assert result.get_column("status").unique().to_list() == ["allocated"]


def test_allocation_basic_replaces_existing_target_and_combines_duplicate_rates() -> None:
    source = pl.DataFrame({"key": ["A"], "department": ["old"], "amount": [10]})
    rates = pl.DataFrame(
        {
            "key": ["A", "A", "A"],
            "department": ["X", "X", None],
            "weight": [1, 1, 2],
        }
    )

    result = DataAllocator().allocation_basic(
        source,
        rates,
        value_left="amount",
        rate_right="weight",
        left_on=["key"],
        replace_right=["department"],
        keep_label=True,
    )

    allocated = result.filter(pl.col("dim_alclabel") == "in").sort("department", nulls_last=True)
    assert allocated.select("department", "amount").to_dicts() == [
        {"department": "X", "amount": 5.0},
        {"department": None, "amount": 5.0},
    ]


def test_allocation_basic_rejects_missing_rate_keys() -> None:
    source = pl.DataFrame({"key": ["A", "B"], "amount": [10, 20]})
    rates = pl.DataFrame({"key": ["A"], "target": ["X"], "weight": [1]})

    with pytest.raises(ValueError, match="必须覆盖左表所有索引"):
        DataAllocator().allocation_basic(
            source,
            rates,
            value_left="amount",
            rate_right="weight",
            left_on=["key"],
            replace_right=["target"],
        )


def test_allocation_basic_calculates_rate_from_largest_allocated_value() -> None:
    source = pl.DataFrame({"key": ["A"], "amount": [100], "profit": [40]})
    rates = pl.DataFrame({"key": ["A", "A"], "target": ["X", "Y"], "weight": [1, 3]})

    result = DataAllocator().allocation_basic(
        source,
        rates,
        value_left=["amount", "profit"],
        rate_right="weight",
        left_on=["key"],
        replace_right=["target"],
        calc_rate_col="allocation_rate",
        keep_label=True,
    )

    assert result.filter(pl.col("dim_alclabel") == "in").sort("target").get_column(
        "allocation_rate"
    ).to_list() == [0.25, 0.75]


def test_allocation_family_uses_rules_in_order_and_returns_missing_rows() -> None:
    source = pl.DataFrame(
        {
            "level_1": ["A", "A", "B"],
            "level_2": ["A1", None, "B1"],
            "amount": [10, 20, 30],
        }
    )
    rates = pl.DataFrame(
        {
            "level_1": ["A", "A"],
            "level_2": ["A1", "A1"],
            "target": ["X", "Y"],
            "weight": [1, 1],
        }
    )
    rules = [
        {
            "left_on": ["level_1", "level_2"],
            "replace_right": ["target"],
        },
        {"left_on": ["level_1"], "replace_right": ["level_2", "target"]},
    ]

    result, missing = DataAllocator().allocation_family(
        source,
        rates,
        value_left="amount",
        rate_right="weight",
        allocation_list=rules,
        keep_label=True,
    )

    assert missing.to_dicts() == [{"level_1": "B", "level_2": "B1", "amount": 30}]
    assert result.filter(pl.col("dim_alclabel") == "out").height == 2
    assert result.filter(pl.col("dim_alclabel") == "in").height == 4
    assert result.get_column("分摊线索_family").drop_nulls().unique().len() == 2
    assert result.get_column("amount").sum() == pytest.approx(0)


def test_allocation_family_rejects_missing_rows_when_requested() -> None:
    source = pl.DataFrame({"key": ["missing"], "amount": [10]})
    rates = pl.DataFrame({"key": ["A"], "target": ["X"], "weight": [1]})

    with pytest.raises(ValueError, match="有数据未被分摊"):
        DataAllocator().allocation_family(
            source,
            rates,
            value_left="amount",
            rate_right="weight",
            allocation_list=[{"left_on": ["key"], "replace_right": ["target"]}],
            miss_ok=False,
        )


def test_allocation_family_supports_empty_keys_without_leaking_temporary_columns() -> None:
    source = pl.DataFrame({"item": ["A"], "amount": [12]})
    rates = pl.DataFrame({"target": ["X", "Y"], "weight": [1, 2]})

    result, missing = DataAllocator().allocation_family(
        source,
        rates,
        value_left="amount",
        rate_right="weight",
        allocation_list=[{"left_on": [], "replace_right": ["target"]}],
        keep_label=True,
    )

    assert missing.is_empty()
    assert not any(column.startswith("_tmp_allocation") for column in result.columns)
    assert result.filter(pl.col("dim_alclabel") == "in").sort("target").get_column(
        "amount"
    ).to_list() == [4.0, 8.0]
