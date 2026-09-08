import importlib
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin_config_calc.service import append_with_overwrite, concat
from fin_config_calc.utils.function_runner import execute_function
from fin_config_calc.utils.io_dataframe_excel import read_excel


def test_concat_excel_files_reads_processes_and_writes_excel(tmp_path: Path) -> None:
    first_input_path = tmp_path / "first.xlsx"
    second_input_path = tmp_path / "second.xlsx"
    output_path = tmp_path / "output.xlsx"
    pl.DataFrame({"code": ["A"], "amount": [10]}).write_excel(first_input_path)
    pl.DataFrame({"code": ["B"], "amount": [20]}).write_excel(second_input_path)

    result = concat(
        [first_input_path, second_input_path],
        output_path,
    )

    assert result == output_path
    assert read_excel(output_path).to_dict(as_series=False) == {
        "code": ["A", "B"],
        "amount": [10, 20],
    }


def test_concat_excel_files_assigns_source_column_before_concatenating(tmp_path: Path) -> None:
    first_input_path = tmp_path / "first.xlsx"
    second_input_path = tmp_path / "second.xlsx"
    output_path = tmp_path / "output.xlsx"
    pl.DataFrame({"code": ["A"]}).write_excel(first_input_path)
    pl.DataFrame({"code": ["B"]}).write_excel(second_input_path)

    concat(
        [first_input_path, second_input_path],
        output_path,
        source_column="source",
        source_values=["January", "February"],
    )

    assert read_excel(output_path).to_dict(as_series=False) == {
        "code": ["A", "B"],
        "source": ["January", "February"],
    }


def test_concat_mixed_file_formats_and_writes_parquet(tmp_path: Path) -> None:
    excel_input_path = tmp_path / "first.xlsx"
    parquet_input_path = tmp_path / "second.parquet"
    output_path = tmp_path / "output.parquet"
    pl.DataFrame({"code": ["A"], "amount": [10]}).write_excel(excel_input_path)
    pl.DataFrame({"code": ["B"], "amount": [20]}).write_parquet(parquet_input_path)

    result = execute_function(
        "fin_config_calc.service.concat.concat",
        {
            "input_file_paths": [excel_input_path, parquet_input_path],
            "output_file_path": output_path,
        },
    )

    assert result == output_path
    assert pl.read_parquet(output_path).to_dict(as_series=False) == {
        "code": ["A", "B"],
        "amount": [10, 20],
    }


def test_concat_uses_field_union_and_fills_missing_values(tmp_path: Path) -> None:
    first_input_path = tmp_path / "first.parquet"
    second_input_path = tmp_path / "second.parquet"
    output_path = tmp_path / "output.parquet"
    pl.DataFrame({"code": ["A"], "amount": [10]}).write_parquet(first_input_path)
    pl.DataFrame({"code": ["B"], "department": ["Sales"]}).write_parquet(second_input_path)

    result = concat([first_input_path, second_input_path], output_path)

    assert result == output_path
    assert pl.read_parquet(output_path).to_dict(as_series=False) == {
        "code": ["A", "B"],
        "amount": [10, None],
        "department": [None, "Sales"],
    }


def test_append_with_overwrite_replaces_only_matching_database_partition(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.parquet"
    upload_path = tmp_path / "upload.parquet"
    pl.DataFrame(
        {
            "dim_period": ["202601", "202601", "202602"],
            "dim_scenario": ["ACT", "BUD", "ACT"],
            "amount": [10, 20, 30],
        }
    ).write_parquet(database_path)
    pl.DataFrame(
        {
            "dim_period": ["202601", "202601"],
            "dim_scenario": ["ACT", "ACT"],
            "amount": [100, 200],
        }
    ).write_parquet(upload_path)

    result = append_with_overwrite(
        database_path,
        upload_path,
        {"dim_period": "202601", "dim_scenario": "ACT"},
    )

    assert result == database_path
    assert pl.read_parquet(database_path).to_dicts() == [
        {"dim_period": "202601", "dim_scenario": "BUD", "amount": 20},
        {"dim_period": "202602", "dim_scenario": "ACT", "amount": 30},
        {"dim_period": "202601", "dim_scenario": "ACT", "amount": 100},
        {"dim_period": "202601", "dim_scenario": "ACT", "amount": 200},
    ]


def test_append_with_overwrite_logs_row_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "database.parquet"
    upload_path = tmp_path / "upload.parquet"
    pl.DataFrame({"partition": ["A", "B", "B"], "amount": [10, 20, 30]}).write_parquet(
        database_path
    )
    pl.DataFrame({"partition": ["A", "A"], "amount": [100, 200]}).write_parquet(upload_path)
    log_calls: list[tuple[str, tuple[Any, ...]]] = []
    concat_module = importlib.import_module("fin_config_calc.service.concat")
    monkeypatch.setattr(
        concat_module.logger,
        "info",
        lambda message, *args: log_calls.append((message, args)),
    )

    append_with_overwrite(database_path, upload_path, {"partition": "A"})

    assert (
        "数据上传完成：上传前共 {} 行，删除 {} 行，追加 {} 行，上传后共 {} 行。",
        (3, 1, 2, 4),
    ) in log_calls


def test_append_with_overwrite_rejects_upload_outside_partition_without_writing(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.parquet"
    upload_path = tmp_path / "upload.parquet"
    original = pl.DataFrame(
        {
            "dim_period": ["202601", "202602"],
            "dim_scenario": ["ACT", "ACT"],
            "amount": [10, 20],
        }
    )
    original.write_parquet(database_path)
    pl.DataFrame(
        {
            "dim_period": ["202601", "202602"],
            "dim_scenario": ["ACT", "ACT"],
            "amount": [100, 200],
        }
    ).write_parquet(upload_path)

    with pytest.raises(ValueError, match="不满足 overwrite_conditions"):
        append_with_overwrite(
            database_path,
            upload_path,
            {"dim_period": "202601", "dim_scenario": "ACT"},
        )

    assert pl.read_parquet(database_path).equals(original)


def test_append_with_overwrite_updates_named_excel_sheet(tmp_path: Path) -> None:
    database_path = tmp_path / "database.xlsx"
    upload_path = tmp_path / "upload.xlsx"
    pl.DataFrame({"dim_period": ["202601", "202602"], "amount": [10, 20]}).write_excel(
        database_path, worksheet="Data"
    )
    pl.DataFrame({"dim_period": ["202601"], "amount": [100]}).write_excel(
        upload_path,
        worksheet="Upload",
    )

    append_with_overwrite(
        database_path,
        upload_path,
        {"dim_period": "202601"},
        database_sheet_name="Data",
        upload_sheet_name="Upload",
    )

    assert read_excel(database_path, "Data").to_dicts() == [
        {"dim_period": "202602", "amount": 20},
        {"dim_period": "202601", "amount": 100},
    ]
