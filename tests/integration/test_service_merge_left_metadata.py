from pathlib import Path

import polars as pl

from fin_config_calc.utils.function_runner import execute_function
from fin_config_calc.utils.io_dataframe_excel import read_excel


def test_merge_left_metadata_reads_two_sheets_and_writes_result(tmp_path: Path) -> None:
    input_path = tmp_path / "input.xlsx"
    metadata_path = tmp_path / "parameters.xlsx"
    output_path = tmp_path / "output.xlsx"
    pl.DataFrame(
        {
            "account": ["1001", "1002"],
            "entity": ["E1", "E2"],
            "amount": [10, 20],
        }
    ).write_excel(input_path, worksheet="data")
    pl.DataFrame(
        {
            "dimension": ["d_account", "d_account", "d_entity", "d_entity"],
            "element_code": ["1001", "1002", "E1", "E2"],
            "element_name": ["现金", "银行存款", "总部", "分部"],
            "parent": ["1000", "1000", None, "E1"],
        }
    ).write_excel(metadata_path, worksheet="维度元数据")
    relations = """
        {
            "account": {
                "dimension": "d_account",
                "attributes": {
                    "element_name": "account_name",
                    "parent": "account_parent"
                }
            },
            "entity": {
                "dimension": "d_entity",
                "attributes": {"element_name": "entity_name"}
            }
        }
    """

    result = execute_function(
        "fin_config_calc.service.merge_left_metadata.merge_left_metadata",
        {
            "input_file_path": input_path,
            "metadata_file_path": metadata_path,
            "relations": relations,
            "output_file_path": output_path,
            "input_sheet_name": "data",
            "metadata_sheet_name": "维度元数据",
        },
    )

    assert result == output_path
    assert read_excel(output_path).to_dict(as_series=False) == {
        "account": ["1001", "1002"],
        "entity": ["E1", "E2"],
        "amount": [10, 20],
        "account_name": ["现金", "银行存款"],
        "account_parent": ["1000", "1000"],
        "entity_name": ["总部", "分部"],
    }
