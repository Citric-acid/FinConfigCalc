from pathlib import Path

import polars as pl
import pytest

from fin_config_calc.service.check_metadata import check_metadata


def test_check_metadata_writes_data_validation_errors_then_stops(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    metadata_path = tmp_path / "metadata.parquet"
    output_path = tmp_path / "errors.parquet"
    pl.DataFrame({"account": ["1001", "TOTAL"]}).write_parquet(input_path)
    pl.DataFrame(
        {
            "dimension": ["account", "account"],
            "element_code": ["TOTAL", "1001"],
            "element_name": ["Total", "Cash"],
            "is_base": ["N", "Y"],
            "parent": [None, "TOTAL"],
        }
    ).write_parquet(metadata_path)

    with pytest.raises(ValueError, match="待检测数据元数据合法性校验失败"):
        check_metadata(input_path, metadata_path, output_path)

    assert pl.read_parquet(output_path).to_dicts() == [
        {
            "account": "TOTAL",
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": "TOTAL",
            "REASON": "合法性校验失败",
        }
    ]


def test_check_metadata_stops_when_metadata_is_invalid(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    metadata_path = tmp_path / "metadata.parquet"
    output_path = tmp_path / "errors.parquet"
    pl.DataFrame({"account": ["1001"]}).write_parquet(input_path)
    pl.DataFrame(
        {
            "dimension": ["account"],
            "element_code": ["1001"],
            "element_name": ["Cash"],
            "is_base": ["Y"],
            "parent": ["MISSING"],
        }
    ).write_parquet(metadata_path)

    with pytest.raises(ValueError, match="元数据校验失败"):
        check_metadata(input_path, metadata_path, output_path)

    assert not output_path.exists()
