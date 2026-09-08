from pathlib import Path

import polars as pl
import pytest

from fin_config_calc.utils.io_dataframe import read_dataframe, write_dataframe


@pytest.mark.parametrize("suffix", [".xlsx", ".parquet"])
def test_write_and_read_dataframe_by_file_suffix(tmp_path: Path, suffix: str) -> None:
    expected = pl.DataFrame({"code": ["A", "B"], "amount": [10, 20]})
    output_path = tmp_path / "nested" / f"output{suffix}"

    result = write_dataframe(expected, output_path)

    assert result == output_path
    assert read_dataframe(output_path).equals(expected)


def test_read_dataframe_rejects_sheet_name_for_parquet(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    pl.DataFrame({"amount": [10]}).write_parquet(input_path)

    with pytest.raises(ValueError, match="Parquet 文件不支持 sheet_name"):
        read_dataframe(input_path, "Sheet1")


@pytest.mark.parametrize("file_name", ["input.csv", "input"])
def test_read_dataframe_rejects_unsupported_format(tmp_path: Path, file_name: str) -> None:
    with pytest.raises(ValueError, match="不支持的输入文件格式"):
        read_dataframe(tmp_path / file_name)


@pytest.mark.parametrize("file_name", ["output.csv", "output.xlsm", "output"])
def test_write_dataframe_rejects_unsupported_format(tmp_path: Path, file_name: str) -> None:
    with pytest.raises(ValueError, match="不支持的输出文件格式"):
        write_dataframe(pl.DataFrame({"amount": [10]}), tmp_path / file_name)
