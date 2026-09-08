from pathlib import Path

import polars as pl

from fin_config_calc.utils.function_runner import execute_function


def test_unpivot_allows_omitting_sheet_name_for_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "result.parquet"
    pl.DataFrame({"account": ["A"], "January": [10], "February": [20]}).write_parquet(input_path)

    result = execute_function(
        "fin_config_calc.service.unpivot.unpivot",
        {
            "input_file_path": input_path,
            "unpivot_columns": ["January", "February"],
            "variable_column": "month",
            "value_column": "amount",
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).to_dict(as_series=False) == {
        "account": ["A", "A"],
        "month": ["January", "February"],
        "amount": [10, 20],
    }
