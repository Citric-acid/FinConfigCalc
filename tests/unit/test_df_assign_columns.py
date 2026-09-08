import polars as pl
import pytest

from fin_config_calc.utils.df_assign_columns import assign_columns


def test_assign_columns_adds_multiple_constant_values() -> None:
    dataframe = pl.DataFrame({"amount": [10, 20]})

    result = assign_columns(dataframe, {"source": "budget", "version": 1})

    assert result.to_dict(as_series=False) == {
        "amount": [10, 20],
        "source": ["budget", "budget"],
        "version": [1, 1],
    }


def test_assign_columns_overwrites_existing_column() -> None:
    dataframe = pl.DataFrame({"amount": [10, 20]})

    result = assign_columns(dataframe, {"amount": 0})

    assert result.to_dict(as_series=False) == {"amount": [0, 0]}


@pytest.mark.parametrize("column_values", [{}, {"": "budget"}, {"   ": "budget"}, {1: "budget"}])
def test_assign_columns_requires_valid_column_value_mapping(column_values: object) -> None:
    dataframe = pl.DataFrame({"amount": [10]})

    with pytest.raises(ValueError):
        assign_columns(dataframe, column_values)  # type: ignore[arg-type]
