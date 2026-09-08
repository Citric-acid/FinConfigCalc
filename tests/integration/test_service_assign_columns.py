from pathlib import Path

import polars as pl

from fin_config_calc.service import assign_columns
from fin_config_calc.utils.function_runner import execute_function
from fin_config_calc.utils.io_dataframe_excel import read_excel


def test_assign_columns_reads_processes_and_writes_excel(tmp_path: Path) -> None:
    input_path = tmp_path / "input.xlsx"
    output_path = tmp_path / "output.xlsx"
    pl.DataFrame({"amount": [10, 20]}).write_excel(input_path)

    result = assign_columns(input_path, {"source": "budget", "version": 1}, output_path)

    assert result == output_path
    assert read_excel(output_path).to_dict(as_series=False) == {
        "amount": [10, 20],
        "source": ["budget", "budget"],
        "version": [1, 1],
    }


def test_assign_columns_reads_and_writes_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    output_path = tmp_path / "output.parquet"
    pl.DataFrame({"amount": [10, 20]}).write_parquet(input_path)

    result = execute_function(
        "fin_config_calc.service.assign_columns.assign_columns",
        {
            "input_file_path": input_path,
            "column_values": {"source": "budget"},
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).to_dict(as_series=False) == {
        "amount": [10, 20],
        "source": ["budget", "budget"],
    }
