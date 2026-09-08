from pathlib import Path

import polars as pl

from fin_config_calc.utils.function_runner import execute_function


def test_filter_by_conditions_reads_filters_and_writes_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "result.parquet"
    pl.DataFrame(
        {
            "region": ["华东", "华南", "华东"],
            "amount": [50, 200, 300],
        }
    ).write_parquet(input_path)

    result = execute_function(
        "fin_config_calc.service.filter.filter_by_conditions",
        {
            "input_file_path": input_path,
            "conditions": {"region": "华东", "amount": {"ge": 100}},
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).to_dicts() == [{"region": "华东", "amount": 300}]
