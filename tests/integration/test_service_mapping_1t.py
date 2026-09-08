from pathlib import Path

import polars as pl

from fin_config_calc.utils.function_runner import execute_function


def test_mapping_1t_allows_omitting_sheet_names_for_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    config_path = tmp_path / "mapping.parquet"
    output_path = tmp_path / "output.parquet"
    pl.DataFrame({"material": ["A"]}).write_parquet(input_path)
    pl.DataFrame(
        {
            "order_execution": [1],
            "priority": [1],
            "mapping_code": ["material-a"],
            "keep_row": ["是"],
            "source_field_1": ["material"],
            "source_code_1": ["A"],
            "output_field_1": ["segment"],
            "output_code_1": ["north"],
        }
    ).write_parquet(config_path)

    result = execute_function(
        "fin_config_calc.service.mapping_1t.mapping_1t",
        {
            "input_file_path": input_path,
            "config_file_path": config_path,
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).get_column("segment").to_list() == ["north"]
