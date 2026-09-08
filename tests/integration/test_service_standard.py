from pathlib import Path

import polars as pl

from fin_config_calc.utils.function_runner import execute_function


def test_standardize_columns_allows_omitting_sheet_names_for_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    config_path = tmp_path / "rules.parquet"
    output_path = tmp_path / "standardized.parquet"
    pl.DataFrame({"amount": ["10", "20"]}).write_parquet(input_path)
    pl.DataFrame(
        {
            "field_name": ["amount"],
            "standard": ["value"],
            "dtype": ["float"],
        }
    ).write_parquet(config_path)

    result = execute_function(
        "fin_config_calc.service.standardize_columns.standardize_columns",
        {
            "input_file_path": input_path,
            "config_file_path": config_path,
            "field_name": "field_name",
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).to_dict(as_series=False) == {"value": [10.0, 20.0]}
