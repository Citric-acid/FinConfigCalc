from pathlib import Path

from fin_config_calc.service import standardize_columns, unpivot

if __name__ == "__main__":
    FIXTURE_DIR = Path(__file__).resolve().parent / "fixture"
    tmp_dir = FIXTURE_DIR / "tmp"
    config_path = FIXTURE_DIR / "损益管报参数.xlsx"
    tmp_unpivot_path = tmp_dir / "tmp_unpivot.xlsx"
    tmp_standardize_path = tmp_dir / "tmp_standardize.xlsx"

    # result_unpivot = unpivot(
    #     input_file_path=FIXTURE_DIR / "收支统计.xlsx",
    #     input_sheet_name="Sheet1",
    #     config_file_path=config_path,
    #     config_sheet_name="转置1",
    #     output_file_path=tmp_unpivot_path,
    # )

    # result_standardize = standardize_columns(
    #     input_file_path=result_unpivot,
    #     input_sheet_name="Sheet1",
    #     config_file_path=config_path,
    #     config_sheet_name="列名对齐",
    #     field_name="收入成本登记表",
    #     output_file_path=tmp_standardize_path,
    # )

    result_standardize = standardize_columns(
        input_file_path=FIXTURE_DIR / "回款明细.xlsx",
        input_sheet_name="Sheet1",
        config_file_path=config_path,
        config_sheet_name="列名对齐",
        field_name="回款明细",
        output_file_path=tmp_standardize_path,
    )
