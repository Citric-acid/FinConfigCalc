import polars as pl
import pytest

from fin_config_calc.utils.df_merge_concat import concat_dfs, merge_left_metadata


def test_merge_left_metadata_joins_multiple_dimensions_and_attributes() -> None:
    dataframe = pl.DataFrame(
        {
            "account": ["1001", "1002"],
            "entity": ["E1", "E2"],
            "account_name": ["旧名称1", "旧名称2"],
            "amount": [10, 20],
        }
    )
    metadata = pl.DataFrame(
        {
            "dimension": ["d_account", "d_account", "d_entity", "d_entity"],
            "element_code": ["1001", "1002", "E1", "E2"],
            "element_name": ["现金", "银行存款", "总部", "分部"],
            "is_base": ["Y", "Y", "Y", "Y"],
            "parent": ["1000", "1000", None, "E1"],
        }
    )
    relations = {
        "account": {
            "dimension": "d_account",
            "attributes": {
                "element_name": "account_name",
                "parent": "account_parent",
            },
        },
        "entity": {
            "dimension": "d_entity",
            "attributes": {"element_name": "entity_name"},
        },
    }

    result = merge_left_metadata(dataframe, metadata, relations)

    assert result.to_dict(as_series=False) == {
        "account": ["1001", "1002"],
        "entity": ["E1", "E2"],
        "amount": [10, 20],
        "account_name": ["现金", "银行存款"],
        "account_parent": ["1000", "1000"],
        "entity_name": ["总部", "分部"],
    }


def test_merge_left_metadata_accepts_json_string() -> None:
    dataframe = pl.DataFrame({"account": ["1001"]})
    metadata = pl.DataFrame(
        {
            "dimension": ["d_account"],
            "element_code": ["1001"],
            "element_name": ["现金"],
        }
    )
    relations = """
        {
            "account": {
                "dimension": "d_account",
                "attributes": {"element_name": "account_name"}
            }
        }
    """

    result = merge_left_metadata(dataframe, metadata, relations)

    assert result.to_dicts() == [{"account": "1001", "account_name": "现金"}]


def test_merge_left_metadata_rejects_unknown_dimension() -> None:
    dataframe = pl.DataFrame({"account": ["1001"]})
    metadata = pl.DataFrame(
        {
            "dimension": ["d_account"],
            "element_code": ["1001"],
            "element_name": ["现金"],
        }
    )
    relations = {
        "account": {
            "dimension": "unknown",
            "attributes": {"element_name": "account_name"},
        }
    }

    with pytest.raises(ValueError, match="df_metadata 中不存在维度: unknown"):
        merge_left_metadata(dataframe, metadata, relations)


def test_concat_dfs_appends_rows_in_input_order() -> None:
    first_dataframe = pl.DataFrame({"code": ["A"], "amount": [1]})
    second_dataframe = pl.DataFrame({"code": ["B"], "amount": [2.5]})

    result = concat_dfs([first_dataframe, second_dataframe])

    assert result.to_dict(as_series=False) == {
        "code": ["A", "B"],
        "amount": [1.0, 2.5],
    }


def test_concat_dfs_requires_at_least_one_dataframe() -> None:
    with pytest.raises(ValueError, match="至少需要一个 DataFrame"):
        concat_dfs([])


def test_concat_dfs_uses_field_union_and_fills_missing_values() -> None:
    first_dataframe = pl.DataFrame({"code": ["A"], "amount": [1]})
    second_dataframe = pl.DataFrame({"code": ["B"], "department": ["Sales"]})

    result = concat_dfs([first_dataframe, second_dataframe])

    assert result.to_dict(as_series=False) == {
        "code": ["A", "B"],
        "amount": [1, None],
        "department": [None, "Sales"],
    }
