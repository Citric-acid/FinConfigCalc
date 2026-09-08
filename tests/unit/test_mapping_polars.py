import polars as pl
import pytest

from fin_config_calc.utils.df_mapping_1t import mapping_1t
from fin_config_calc.utils.df_mapping_n import MAPPING_N


def test_mapping_n_applies_priority_variable_and_fallback() -> None:
    input_df = pl.DataFrame(
        {
            "code": ["A", "B", "C"],
            "source": ["source-a", "source-b", "source-c"],
        }
    )
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": ["code", "code", ""],
            "映射优先顺序": [1, 1, 0],
            "映射规则编码": ["rule-a", "rule-b", "fallback"],
            "code": ["A", "B", None],
            "result": ["fixed", "var{source}", "other"],
        }
    )

    result = MAPPING_N(input_df, mapping_df, ["result"]).mapping_all(miss_ok=False)

    assert result.get_column("result").to_list() == ["fixed", "source-b", "other"]
    assert result.get_column("map_trc_result").to_list() == [
        "fallback->rule-a",
        "fallback->rule-b",
        "fallback",
    ]


def test_mapping_n_uses_one_group_per_row_when_only_fallback_exists() -> None:
    input_df = pl.DataFrame({"code": ["A", "B"]})
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": [""],
            "映射优先顺序": [0],
            "映射规则编码": ["fallback"],
            "result": ["default"],
        }
    )

    mapper = MAPPING_N(input_df, mapping_df, ["result"])
    result = mapper.mapping_all()

    assert result.get_column("map_trc_result").to_list() == ["fallback", "fallback"]
    assert mapper.inout_pid_df.get_column("cid").to_list() == [0, 1]
    assert mapper.mapped_best_df.height == 2


def test_mapping_n_uses_last_non_null_value_by_priority() -> None:
    input_df = pl.DataFrame({"code": ["A"]})
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": ["", "code"],
            "映射优先顺序": [0, 1],
            "映射规则编码": ["fallback", "specific"],
            "code": [None, "A"],
            "result": ["fallback-value", None],
        }
    )

    result = MAPPING_N(input_df, mapping_df, ["result"]).mapping_all()

    assert result.get_column("result").to_list() == ["fallback-value"]
    assert result.get_column("map_trc_result").to_list() == ["fallback->specific"]


def test_mapping_n_supports_builtin_expression_context() -> None:
    input_df = pl.DataFrame({"amount": [-2.6]})
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": [""],
            "映射优先顺序": [0],
            "映射规则编码": ["fallback"],
            "result": ["exp{max(abs(amount), round(2.4))}"],
        }
    )

    result = MAPPING_N(input_df, mapping_df, ["result"]).mapping_all()

    assert result.get_column("result").to_list() == [2.6]


def test_mapping_n_preserves_mixed_expression_values_and_converts_none_to_null() -> None:
    input_df = pl.DataFrame({"code": ["A", "B", "C"]})
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": ["code", "code", "code"],
            "映射优先顺序": [1, 1, 1],
            "映射规则编码": ["a", "b", "c"],
            "code": ["A", "B", "C"],
            "result": ["fixed", "exp{2.5}", "exp{None}"],
        }
    )

    result = MAPPING_N(input_df, mapping_df, ["result"]).mapping_all()

    assert result.get_column("result").to_list() == ["fixed", 2.5, None]
    assert result.schema["result"] == pl.Object


@pytest.mark.parametrize("expression", ["exp{NA}", "exp{nan}", "exp{pd.NA}", "exp{np.nan}"])
def test_mapping_n_rejects_legacy_expression_nulls(expression: str) -> None:
    input_df = pl.DataFrame({"code": ["A"]})
    mapping_df = pl.DataFrame(
        {
            "映射规则类型": [""],
            "映射优先顺序": [0],
            "映射规则编码": ["fallback"],
            "result": [expression],
        }
    )

    mapper = MAPPING_N(input_df, mapping_df, ["result"])

    assert not mapper.validate_ok
    assert mapper.validate_df.get_column("REASON").to_list() == [
        "计算表达式不允许使用 NA、nan、pd 或 np，请使用 None 表示空值"
    ]


def test_mapping_1t_splits_configuration_and_filters_rows() -> None:
    input_df = pl.DataFrame({"material": ["A", "B"]})
    mapping_table = pl.DataFrame(
        {
            "order_execution": [1, 1],
            "priority": [1, 1],
            "mapping_code": ["material-a", "material-b"],
            "keep_row": ["是", "否"],
            "source_field_1": ["material", "material"],
            "source_code_1": ["A", "B"],
            "output_field_1": ["segment", "segment"],
            "output_code_1": ["north", "south"],
        }
    )

    result = mapping_1t(input_df, mapping_table, miss_ok=False)

    assert result.to_dicts() == [
        {
            "material": "A",
            "keep_row": "是",
            "map_trc_keep_row": "material-a",
            "map_trc_segment": "material-a",
            "segment": "north",
        }
    ]


def test_mapping_1t_allows_unmatched_rows_by_default() -> None:
    input_df = pl.DataFrame({"material": ["A", "B"]})
    mapping_table = pl.DataFrame(
        {
            "order_execution": [1],
            "priority": [1],
            "mapping_code": ["material-a"],
            "keep_row": ["是"],
            "source_field_1": ["material"],
            "source_code_1": ["A"],
        }
    )

    result = mapping_1t(input_df, mapping_table)

    assert result.get_column("material").to_list() == ["A"]


def test_mapping_1t_applies_rule_without_source_conditions() -> None:
    input_df = pl.DataFrame({"material": ["A", "B"]})
    mapping_table = pl.DataFrame(
        {
            "order_execution": [1],
            "priority": [1],
            "mapping_code": ["keep-all"],
            "keep_row": ["是"],
            "source_field_1": [None],
            "source_code_1": [None],
        }
    )

    result = mapping_1t(input_df, mapping_table, miss_ok=False)

    assert result.get_column("material").to_list() == ["A", "B"]
    assert result.get_column("map_trc_keep_row").to_list() == ["keep-all", "keep-all"]


def test_mapping_1t_executes_order_execution_in_ascending_order() -> None:
    input_df = pl.DataFrame({"code": ["A"]})
    mapping_table = pl.DataFrame(
        {
            "order_execution": [2, 1],
            "priority": [1, 1],
            "mapping_code": ["second", "first"],
            "keep_row": ["是", "是"],
            "source_field_1": ["code", "code"],
            "source_code_1": ["A", "A"],
            "output_field_1": ["result", "result"],
            "output_code_1": ["second-value", "first-value"],
        }
    )

    result = mapping_1t(input_df, mapping_table)

    assert result.get_column("result").to_list() == ["second-value"]


def test_mapping_1t_rejects_unmatched_rows_when_requested() -> None:
    input_df = pl.DataFrame({"material": ["B"]})
    mapping_table = pl.DataFrame(
        {
            "order_execution": [1],
            "priority": [1],
            "mapping_code": ["material-a"],
            "keep_row": ["是"],
            "source_field_1": ["material"],
            "source_code_1": ["A"],
        }
    )

    with pytest.raises(ValueError, match="未命中规则"):
        mapping_1t(input_df, mapping_table, miss_ok=False)
