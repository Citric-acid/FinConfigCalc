from pathlib import Path

import polars as pl

from fin_config_calc.service.allocation import allocation, expand_allocation_factors


def test_expand_allocation_factors_recurses_and_combines_dimensions() -> None:
    factors = pl.DataFrame(
        {
            "out_d_account": ["ACCOUNT_TOTAL"],
            "out_d_dept": ["DEPT_TOTAL"],
            "in_d_project": ["P1"],
            "rate": [1.0],
        }
    )
    metadata = pl.DataFrame(
        {
            "dimension": [
                "d_account",
                "d_account",
                "d_account",
                "d_account",
                "d_dept",
                "d_dept",
                "d_dept",
            ],
            "element_code": [
                "ACCOUNT_TOTAL",
                "ACCOUNT_GROUP",
                "A1",
                "A2",
                "DEPT_TOTAL",
                "D1",
                "D2",
            ],
            "is_base": ["N", "N", "Y", "Y", "N", "Y", "Y"],
            "parent": [
                None,
                "ACCOUNT_TOTAL",
                "ACCOUNT_GROUP",
                "ACCOUNT_GROUP",
                None,
                "DEPT_TOTAL",
                "DEPT_TOTAL",
            ],
        }
    )

    result = expand_allocation_factors(factors, metadata)

    assert result.select("out_d_account", "out_d_dept").rows() == [
        ("A1", "D1"),
        ("A1", "D2"),
        ("A2", "D1"),
        ("A2", "D2"),
    ]


def test_expand_allocation_factors_supports_regular_expression_members() -> None:
    factors = pl.DataFrame(
        {
            "out_d_account": ["reg{^ACCOUNT_(GROUP|DIRECT)$}", "reg{^MISSING$}"],
            "rate": [1.0, 2.0],
        }
    )
    metadata = pl.DataFrame(
        {
            "dimension": ["d_account"] * 5,
            "element_code": [
                "ACCOUNT_TOTAL",
                "ACCOUNT_GROUP",
                "ACCOUNT_A1",
                "ACCOUNT_A2",
                "ACCOUNT_DIRECT",
            ],
            "is_base": ["N", "N", "Y", "Y", "Y"],
            "parent": [
                None,
                "ACCOUNT_TOTAL",
                "ACCOUNT_GROUP",
                "ACCOUNT_GROUP",
                "ACCOUNT_TOTAL",
            ],
        }
    )

    result = expand_allocation_factors(factors, metadata)

    assert result.select("out_d_account", "rate").rows() == [
        ("ACCOUNT_A1", 1.0),
        ("ACCOUNT_A2", 1.0),
        ("ACCOUNT_DIRECT", 1.0),
        ("reg{^MISSING$}", 2.0),
    ]


def test_allocation_uses_each_factor_group_as_an_independent_scope(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    factor_path = tmp_path / "factor.parquet"
    metadata_path = tmp_path / "metadata.parquet"
    output_path = tmp_path / "output.parquet"
    pl.DataFrame(
        {
            "d_account": ["A1", "A1"],
            "d_dept": ["D1", "D2"],
            "d_project": ["ORIGINAL", "ORIGINAL"],
            "m_value": [100.0, 200.0],
        }
    ).write_parquet(input_path)
    pl.DataFrame(
        {
            "out_d_account": ["A1", "A1"],
            "out_d_dept": ["D1", None],
            "in_d_project": ["P_SPECIFIC", "P_FALLBACK"],
            "rate": [1.0, 1.0],
        }
    ).write_parquet(factor_path)
    pl.DataFrame(
        {
            "dimension": ["d_account", "d_dept", "d_dept"],
            "element_code": ["A1", "D1", "D2"],
            "is_base": ["Y", "Y", "Y"],
            "parent": [None, None, None],
        }
    ).write_parquet(metadata_path)

    result_path = allocation(
        input_file_path=input_path,
        factor_file_path=factor_path,
        metadata_file_path=metadata_path,
        output_file_path=output_path,
        value_columns="m_value",
        keep_label=True,
    )

    result = pl.read_parquet(result_path)
    allocated = result.filter(pl.col("dim_alclabel") == "in").sort("m_value")
    assert allocated.select("d_dept", "d_project", "m_value").rows() == [
        ("D1", "P_SPECIFIC", 100.0),
        ("D1", "P_FALLBACK", 100.0),
        ("D2", "P_FALLBACK", 200.0),
    ]
    assert result.get_column("m_value").sum() == 0


def test_allocation_ignores_rows_outside_factor_scope(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    factor_path = tmp_path / "factor.parquet"
    metadata_path = tmp_path / "metadata.parquet"
    output_path = tmp_path / "output.parquet"
    factor_output_path = tmp_path / "expanded_factor.parquet"
    pl.DataFrame({"d_account": ["MISSING"], "m_value": [100.0]}).write_parquet(input_path)
    pl.DataFrame(
        {"out_d_account": ["TOTAL"], "in_d_account": ["TARGET"], "rate": [1.0]}
    ).write_parquet(factor_path)
    pl.DataFrame(
        {
            "dimension": ["d_account", "d_account"],
            "element_code": ["TOTAL", "A1"],
            "is_base": ["N", "Y"],
            "parent": [None, "TOTAL"],
        }
    ).write_parquet(metadata_path)

    result_path = allocation(
        input_file_path=input_path,
        factor_file_path=factor_path,
        metadata_file_path=metadata_path,
        output_file_path=output_path,
        value_columns="m_value",
        factor_output_file_path=factor_output_path,
    )

    assert pl.read_parquet(factor_output_path).to_dicts() == [
        {"out_d_account": "A1", "in_d_account": "TARGET", "rate": 1.0}
    ]
    assert result_path == output_path
    output = pl.read_parquet(output_path)
    assert output.is_empty()
    assert "d_account" in output.columns


def test_allocation_filters_factors_and_assigns_result_columns(tmp_path: Path) -> None:
    input_path = tmp_path / "input.parquet"
    factor_path = tmp_path / "factor.parquet"
    metadata_path = tmp_path / "metadata.parquet"
    output_path = tmp_path / "output.parquet"
    factor_output_path = tmp_path / "expanded_factor.parquet"
    pl.DataFrame(
        {
            "d_account": ["A1", "A2"],
            "d_project": ["ORIGINAL", "ORIGINAL"],
            "m_value": [100.0, 200.0],
        }
    ).write_parquet(input_path)
    pl.DataFrame(
        {
            "allocation_code": ["PLAN_A", "PLAN_B"],
            "out_d_account": ["A1", "A2"],
            "in_d_project": ["P1", "P2"],
            "rate": [1.0, 1.0],
        }
    ).write_parquet(factor_path)
    pl.DataFrame(
        {
            "dimension": ["d_account", "d_account"],
            "element_code": ["A1", "A2"],
            "is_base": ["Y", "Y"],
            "parent": [None, None],
        }
    ).write_parquet(metadata_path)

    allocation(
        input_file_path=input_path,
        factor_file_path=factor_path,
        metadata_file_path=metadata_path,
        output_file_path=output_path,
        value_columns="m_value",
        factor_query={"allocation_code": "PLAN_B"},
        assign_result={"scenario": "budget", "version": 2},
        factor_output_file_path=factor_output_path,
        keep_label=True,
    )

    assert pl.read_parquet(factor_output_path).get_column("allocation_code").to_list() == ["PLAN_B"]
    result = pl.read_parquet(output_path)
    assert result.filter(pl.col("dim_alclabel") == "in").select(
        "d_account", "d_project", "m_value"
    ).rows() == [("A2", "P2", 200.0)]
    assert result.get_column("scenario").unique().to_list() == ["budget"]
    assert result.get_column("version").unique().to_list() == [2]
