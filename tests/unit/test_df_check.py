import polars as pl

from fin_config_calc.utils.df_check import df_check_metadata, df_check_metadata_validity


def test_df_check_metadata_validity_reports_all_definition_errors() -> None:
    metadata_df = pl.DataFrame(
        {
            "dimension": ["account", "account", "account", "account", "entity", "entity"],
            "element_code": ["TOTAL", "1001", "1001", "1002", "E1", "E2"],
            "element_name": ["Total", "", "Cash", "Expense", None, "Entity 2"],
            "is_base": ["N", "Y", "Y", "X", None, "Y"],
            "parent": [None, "TOTAL", "TOTAL", "1001", None, "MISSING"],
        }
    )

    result = df_check_metadata_validity(metadata_df)

    assert result.to_dicts() == [
        {
            "dimension": "account",
            "element_code": "1001",
            "REASON": "dimension、element_code 组合不允许重复",
        },
        {
            "dimension": "account",
            "element_code": "1001",
            "REASON": "element_name 不允许为空",
        },
        {
            "dimension": "account",
            "element_code": "1002",
            "REASON": "is_base 只能是 Y 或 N",
        },
        {
            "dimension": "account",
            "element_code": "1002",
            "REASON": "parent 对应元素的 is_base 必须为 N",
        },
        {
            "dimension": "entity",
            "element_code": "E1",
            "REASON": "element_name 不允许为空",
        },
        {
            "dimension": "entity",
            "element_code": "E1",
            "REASON": "is_base 不允许为空",
        },
        {
            "dimension": "entity",
            "element_code": "E2",
            "REASON": "parent 必须存在于同维度的 element_code",
        },
    ]


def test_df_check_metadata_only_accepts_base_elements() -> None:
    metadata_df = pl.DataFrame(
        {
            "dimension": ["account", "account", "entity"],
            "element_code": ["TOTAL", "1001", "E1"],
            "element_name": ["Total", "Cash", "Entity 1"],
            "is_base": ["N", "Y", "Y"],
            "parent": [None, "TOTAL", None],
        }
    )
    dataframe = pl.DataFrame(
        {
            "source_row": [1, 2, 3, 4, 5, 6],
            "account": ["1001", "TOTAL", "9999", "9999", None, "var{account}"],
            "entity": ["E1", "E1", "E1", "E1", "E1", "E1"],
            "amount": [10, 20, 30, 40, 50, 60],
        }
    )

    result = df_check_metadata(dataframe, metadata_df)

    assert result.to_dicts() == [
        {
            "source_row": 2,
            "account": "TOTAL",
            "entity": "E1",
            "amount": 20,
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": "TOTAL",
            "REASON": "合法性校验失败",
        },
        {
            "source_row": 3,
            "account": "9999",
            "entity": "E1",
            "amount": 30,
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": "9999",
            "REASON": "合法性校验失败",
        },
        {
            "source_row": 4,
            "account": "9999",
            "entity": "E1",
            "amount": 40,
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": "9999",
            "REASON": "合法性校验失败",
        },
        {
            "source_row": 5,
            "account": None,
            "entity": "E1",
            "amount": 50,
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": None,
            "REASON": "不允许为空值",
        },
    ]


def test_df_check_metadata_reports_missing_dimension_column() -> None:
    metadata_df = pl.DataFrame(
        {
            "dimension": ["account"],
            "element_code": ["1001"],
            "element_name": ["Cash"],
            "is_base": ["Y"],
            "parent": [None],
        }
    )

    result = df_check_metadata(pl.DataFrame({"amount": [1]}), metadata_df)

    assert result.to_dicts() == [
        {
            "amount": None,
            "CHECK_DIMENSION": "account",
            "CHECK_ELEMENT_CODE": None,
            "REASON": "待检测数据缺少维度字段",
        }
    ]


def test_df_check_metadata_empty_result_preserves_input_schema() -> None:
    metadata_df = pl.DataFrame(
        {
            "dimension": ["account"],
            "element_code": ["1001"],
            "element_name": ["Cash"],
            "is_base": ["Y"],
            "parent": [None],
        }
    )
    dataframe = pl.DataFrame({"account": ["1001"], "amount": [10]})

    result = df_check_metadata(dataframe, metadata_df)

    assert result.is_empty()
    assert result.schema == {
        "account": pl.String,
        "amount": pl.Int64,
        "CHECK_DIMENSION": pl.String,
        "CHECK_ELEMENT_CODE": pl.String,
        "REASON": pl.String,
    }
