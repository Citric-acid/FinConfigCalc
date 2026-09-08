"""基于 Polars 的多条件映射实现。

本模块迁移自 ``D:/Codes/fdt_paw_apportion/utils/df_mapping_n.py``，但不是原实现的
逐行同步副本，主要区别如下：

- 输入、映射表、校验结果和映射结果均使用 Polars DataFrame，不接受 Pandas DataFrame。
- 不依赖原项目的 ``config``、分组/合并工具、OSS 或飞书通知；映射失败仅记录日志或抛出异常。
- 规则表达式以 ``exp{None}`` 表示空值，禁止使用 ``NA``、``nan``、``pd`` 和 ``np``；
    ``round`` 使用 Python 内置函数。
- 分组、等值匹配和结果聚合优先使用 Polars 表达式；仅正则规则和动态值计算进入 Python
    行级逻辑，并显式处理 Polars 类型推断。

两版保留相同的核心规则格式、优先级语义、映射轨迹字段及 ``miss_ok`` 行为，但新增或修改
规则时应分别验证，不应假定两个实现对所有边界值完全等价。
"""

import ast
import collections
import re
import uuid
from typing import Any

import arrow
import polars as pl
from loguru import logger


class MAPPING_N:
    """按优先级将多条件映射规则应用到输入数据。"""

    input_pid = "_tmp_mapping_pid"
    rule_pid = "_tmp_rule_pid"
    map_grp_pid = "_tmp_mapping_grp_pid"
    map_code = "映射规则编码"
    map_priority = "映射优先顺序"
    map_dimensions = "映射规则类型"

    def __init__(
        self,
        input_df: pl.DataFrame,
        mapping_df: pl.DataFrame,
        need_fields: list[str],
        validate_only: bool = False,
        drop_if_exists: bool = True,
    ) -> None:
        """初始化映射器，输入和映射表均使用 Polars DataFrame。"""
        self.need_fields = need_fields
        self.validate_only = validate_only
        self.map_trace_fields = [f"map_trc_{field}" for field in need_fields]
        self.map_trace_field = "map_trc_validate" if validate_only else self.map_trace_fields[0]
        self.mapped_fields = [*need_fields, self.map_code, self.map_priority]

        self.input_df = input_df.with_row_index(self.input_pid)
        existing_fields = set(input_df.columns) & set(need_fields + self.map_trace_fields)
        if existing_fields:
            if not drop_if_exists:
                message = f"input_df 中已存在字段: {existing_fields}"
                logger.error(message)
                raise ValueError(message)
            self.input_df = self.input_df.drop(sorted(existing_fields))

        self.map_base_cols = {
            "rule_dimension": self.map_dimensions,
            "priority": self.map_priority,
            "mapping_code": self.map_code,
        }
        self.mapping_df = mapping_df.rename(
            {
                source: target
                for source, target in self.map_base_cols.items()
                if source in mapping_df.columns
            }
        )
        if self.map_dimensions in self.mapping_df.columns:
            self.mapping_df = self.mapping_df.with_columns(
                pl.when(pl.col(self.map_dimensions).is_null())
                .then(pl.lit("nan"))
                .otherwise(pl.col(self.map_dimensions).cast(pl.Utf8))
                .alias(self.rule_pid)
            )
        else:
            self.mapping_df = self.mapping_df.with_columns(pl.lit("").alias(self.rule_pid))

        if not validate_only and self.map_dimensions in self.mapping_df.columns:
            self.before_mapping()
        self.mapping_rules = self.get_mapping_rules()
        self.validate_ok, self.validate_df = self.validate_data()
        self.validate_text_msg = ""
        if not self.validate_ok:
            self.validate_text_msg = f"校验不通过, 请检查数据:\n{self.validate_df}"
            logger.error(self.validate_text_msg)

    def _prepare_input_groups(self) -> None:
        dimensions = list(
            dict.fromkeys(
                dimension
                for rule_type in self.mapping_df.get_column(self.map_dimensions).to_list()
                if rule_type not in (None, "")
                for dimension in str(rule_type).split("+")
            )
        )
        missing_columns = set(dimensions) - set(self.input_df.columns)
        if missing_columns:
            raise ValueError(f"输入表中缺少映射字段: {missing_columns}")
        if not dimensions:
            self.grp_input_df = self.input_df.with_columns(
                pl.col(self.input_pid).alias(self.map_grp_pid)
            )
            self.input_df = self.grp_input_df
            self.inout_pid_df = self.input_df.select(
                pl.lit("tmp").alias("type_cid"),
                pl.col(self.input_pid).alias("from_pid"),
                pl.col(self.map_grp_pid).alias("cid"),
            )
            return

        group_mapping = (
            self.input_df.select(dimensions)
            .unique(maintain_order=True)
            .with_row_index(self.map_grp_pid)
        )
        self.grp_input_df = group_mapping
        self.input_df = self.input_df.join(
            group_mapping,
            on=dimensions,
            how="left",
            nulls_equal=True,
        )
        self.inout_pid_df = self.input_df.select(
            pl.lit("tmp").alias("type_cid"),
            pl.col(self.input_pid).alias("from_pid"),
            pl.col(self.map_grp_pid).alias("cid"),
        )

    def before_mapping(self) -> None:
        """准备输入数据的映射分组及行到分组的对应关系。"""
        self._prepare_input_groups()

    def _get_mapping_rules(self) -> dict[str, pl.DataFrame]:
        return {
            str(rule_type): self.mapping_df.filter(pl.col(self.rule_pid) == rule_type)
            for rule_type in sorted(
                self.mapping_df.get_column(self.rule_pid).unique().to_list(), key=str
            )
        }

    def get_mapping_rules(self) -> dict[str, pl.DataFrame]:
        """按映射规则类型拆分映射表。"""
        return self._get_mapping_rules()

    def validate_data(self) -> tuple[bool, pl.DataFrame]:
        """校验映射表的必要字段、规则唯一性和变量引用。"""
        results: dict[str, list[str]] = collections.defaultdict(list)
        required = [self.map_code, self.map_priority, self.map_dimensions]
        missing_columns = [column for column in required if column not in self.mapping_df.columns]
        if missing_columns:
            results["映射表缺少必要字段"] = missing_columns
            return False, self._validation_frame(results)

        duplicate_codes = self.mapping_df.filter(~pl.col(self.map_code).is_first_distinct())
        if not duplicate_codes.is_empty():
            results["映射规则编码值不允许重复"] = [
                str(value) for value in duplicate_codes.get_column(self.map_code).to_list()
            ]

        priorities: dict[Any, set[str]] = collections.defaultdict(set)
        for rule_df in self.mapping_rules.values():
            rule_type = rule_df.item(0, self.map_dimensions)
            if rule_type in (None, ""):
                continue
            priorities[rule_df.item(0, self.map_priority)].add(str(rule_type))
            dimensions = str(rule_type).split("+")
            if any(column not in rule_df.columns for column in dimensions):
                results["映射规则类型对应的字段必须存在"].append(str(rule_type))
                continue
            if rule_df.select(
                pl.any_horizontal(
                    pl.col(dimensions).is_null() | (pl.col(dimensions).cast(pl.Utf8) == "")
                ).any()
            ).item():
                results["映射规则类型对应的字段必须有值"].append(str(rule_type))
            if rule_df.select(pl.struct(dimensions).is_duplicated().any()).item():
                results["同一个映射规则类型下的映射条件组合不允许重复"].append(str(rule_type))

        for rule_types in priorities.values():
            if len(rule_types) > 1:
                results["不同映射规则类型优先级不允许相同"].append(str(rule_types))

        if (
            not self.validate_only
            and self.need_fields
            and self.need_fields[0] in self.mapping_df.columns
        ):
            variables = {
                match.group(1)
                for value in self.mapping_df.get_column(self.need_fields[0]).drop_nulls().to_list()
                if (match := re.fullmatch(r"var\{(.*)\}(?:->reg\{.*\})?", str(value).strip()))
            }
            missing_variables = variables - set(self.input_df.columns)
            if missing_variables:
                results[f"映射字段 {self.need_fields[0]} 中的变量值未出现在输入表中"] = sorted(
                    missing_variables
                )

        forbidden_expression_names = {"NA", "nan", "pd", "np"}
        for field in self.need_fields:
            if field not in self.mapping_df.columns:
                continue
            for value in self.mapping_df.get_column(field).drop_nulls().to_list():
                match = re.fullmatch(r"exp\{(.*)\}", str(value).strip())
                if match is None:
                    continue
                try:
                    expression = ast.parse(match.group(1), mode="eval")
                except SyntaxError:
                    continue
                used_names = {
                    node.id for node in ast.walk(expression) if isinstance(node, ast.Name)
                }
                if used_names & forbidden_expression_names:
                    results["计算表达式不允许使用 NA、nan、pd 或 np，请使用 None 表示空值"].append(
                        str(value)
                    )

        validation_df = self._validation_frame(results)
        return validation_df.is_empty(), validation_df

    @staticmethod
    def _validation_frame(results: dict[str, list[str]]) -> pl.DataFrame:
        return pl.DataFrame(
            [
                pl.Series("REASON", list(results), dtype=pl.Utf8),
                pl.Series("VALUE", list(results.values()), dtype=pl.Object),
            ]
        )

    @staticmethod
    def _matches_row(
        input_row: dict[str, Any], rule_row: dict[str, Any], dimensions: list[str]
    ) -> bool:
        for column in dimensions:
            rule_value = str(rule_row[column])
            input_value = "" if input_row[column] is None else str(input_row[column])
            if "reg{" in rule_value:
                match = re.fullmatch(r"reg\{(.*)\}", rule_value.strip())
                if match is None or re.search(match.group(1), input_value) is None:
                    return False
            elif input_value != rule_value:
                return False
        return True

    def match_by_row(
        self,
        input_row: dict[str, Any],
        rule_row: dict[str, Any],
        merge_on: list[str],
    ) -> bool:
        """判断输入行是否命中包含正则条件的映射规则。"""
        return self._matches_row(input_row, rule_row, merge_on)

    def mapping_one(self, rule_df: pl.DataFrame) -> pl.DataFrame:
        """应用一种条件组合的映射规则。"""
        output_columns = [self.map_grp_pid, *self.mapped_fields]
        rule_type = rule_df.item(0, self.map_dimensions)
        if rule_type in (None, ""):
            values = rule_df.row(0, named=True)
            return self.grp_input_df.select(self.map_grp_pid).with_columns(
                [pl.lit(values[field]).alias(field) for field in self.mapped_fields]
            )

        dimensions = str(rule_type).split("+")
        input_df = self.grp_input_df.with_columns(pl.col(dimensions).fill_null("").cast(pl.Utf8))
        rule_df = rule_df.with_columns(pl.col(dimensions).fill_null("").cast(pl.Utf8))
        regular_mask = pl.any_horizontal(pl.col(dimensions).str.contains(r"reg\{"))
        matches: list[pl.DataFrame] = []
        direct_rules = rule_df.filter(~regular_mask)
        if not direct_rules.is_empty():
            matches.append(
                input_df.join(direct_rules, on=dimensions, how="inner").select(output_columns)
            )

        for rule_row in rule_df.filter(regular_mask).iter_rows(named=True):
            matched_rows = input_df.filter(
                pl.struct(dimensions).map_elements(
                    lambda row, current_rule=rule_row: self._matches_row(
                        row, current_rule, dimensions
                    ),
                    return_dtype=pl.Boolean,
                )
            ).select(self.map_grp_pid)
            if not matched_rows.is_empty():
                matches.append(
                    matched_rows.with_columns(
                        [pl.lit(rule_row[field]).alias(field) for field in self.mapped_fields]
                    )
                )

        if matches:
            return pl.concat(matches, how="diagonal_relaxed").select(output_columns)
        return pl.DataFrame(schema={column: pl.Null for column in output_columns})

    @staticmethod
    def apply_value(row: dict[str, Any], field: str) -> Any:
        """计算规则中的固定值、变量引用、正则提取或表达式。"""
        value = row[field]
        text = str(value)
        if "exp{" in text:
            match = re.fullmatch(r"exp\{(.*)\}", text.strip())
            if match is None:
                raise ValueError(f"表达式格式不正确: {value!r}")

            builtins = {
                "len": len,
                "sum": sum,
                "str": str,
                "int": int,
                "float": float,
                "abs": abs,
                "max": max,
                "min": min,
                "round": round,
            }
            if "__UUID__" in match.group(1):
                builtins["__UUID__"] = uuid.uuid4().hex

            expression_context = {
                name: (0 if item is None or (isinstance(item, str) and not item.strip()) else item)
                for name, item in row.items()
            }

            return eval(
                match.group(1),
                {
                    "__builtins__": {},
                    "arrow": arrow,
                },
                {**builtins, **expression_context},
            )
        if "var{" not in text:
            return value
        if "reg{" in text:
            match = re.fullmatch(r"var\{(.*)\}->reg\{(.*)\}", text.strip())
            if match is None:
                raise ValueError(f"变量正则格式不正确: {value!r}")
            extracted_value = re.search(match.group(2), str(row[match.group(1)]))
            if extracted_value is None:
                raise ValueError(f"变量正则未匹配: {value!r}")
            return extracted_value.group(1)
        match = re.fullmatch(r"var\{(.*)\}", text.strip())
        if match is None:
            raise ValueError(f"变量格式不正确: {value!r}")
        return row[match.group(1)]

    @staticmethod
    def _dynamic_value_columns(field: str, values: list[Any], columns: list[str]) -> list[str]:
        """返回计算动态值时需要传给 Python 回调的最小列集合。"""
        required_columns = {field}
        for value in values:
            text = str(value).strip()
            variable_match = re.fullmatch(r"var\{(.*)\}(?:->reg\{.*\})?", text)
            if variable_match is not None:
                required_columns.add(variable_match.group(1))
                continue
            expression_match = re.fullmatch(r"exp\{(.*)\}", text)
            if expression_match is None:
                continue
            try:
                expression = ast.parse(expression_match.group(1), mode="eval")
            except SyntaxError:
                continue
            required_columns.update(
                node.id for node in ast.walk(expression) if isinstance(node, ast.Name)
            )
        return [column for column in columns if column in required_columns]

    @staticmethod
    def _dynamic_value_dtype(
        values: list[Any], schema: dict[str, pl.DataType]
    ) -> pl.DataType | None:
        """纯 ``var{列}`` 规则时沿用被引用列类型，避免 Python UDF 错误推断。"""
        source_columns: list[str] = []
        for value in values:
            match = re.fullmatch(r"var\{(.*)\}", str(value).strip())
            if match is None or match.group(1) not in schema:
                return None
            source_columns.append(match.group(1))

        source_dtypes = {schema[column] for column in source_columns}
        return source_dtypes.pop() if len(source_dtypes) == 1 else None

    @staticmethod
    def _dynamic_value_series(
        field: str,
        values: list[Any],
        dtype: pl.DataType | None,
    ) -> pl.Series:
        """构造动态结果列，并在必要时保留混合值语义。"""
        if dtype is not None:
            return pl.Series(field, values, dtype=dtype, strict=False)
        try:
            return pl.Series(field, values)
        except (TypeError, pl.exceptions.PolarsError):
            return pl.Series(field, values, dtype=pl.Object)

    def mapping_all(self, miss_ok: bool = True) -> pl.DataFrame:
        """应用全部映射规则，并保留输入行的原始顺序。"""
        drop_columns = [self.input_pid, self.map_grp_pid, self.rule_pid]
        if not self.validate_ok:
            raise ValueError(self.validate_text_msg)
        if self.input_df.is_empty():
            result = self.input_df.with_columns(
                [
                    pl.lit(None).alias(column)
                    for field in self.need_fields
                    for column in (field, f"map_trc_{field}")
                ]
            ).drop([column for column in drop_columns if column in self.input_df.columns])
            logger.info("多条件映射完成：输入为空，输出 0 行。")
            return result

        mapped_frames = [self.mapping_one(rule_df) for rule_df in self.mapping_rules.values()]
        mapped_full_df = pl.concat(mapped_frames, how="diagonal_relaxed").sort(
            [self.map_grp_pid, self.map_priority], nulls_last=True
        )
        aggregations = [
            pl.col(field).drop_nulls().last().alias(field) for field in self.need_fields
        ]
        aggregations.append(pl.col(self.map_code).str.join("->").alias(self.map_trace_field))
        self.mapped_best_df = mapped_full_df.group_by(self.map_grp_pid).agg(aggregations)
        self.mapped_best_df = self.mapped_best_df.with_columns(
            [pl.col(self.map_trace_field).alias(column) for column in self.map_trace_fields[1:]]
        )

        missed_rows = self.input_df.join(
            self.mapped_best_df.select(self.map_grp_pid), on=self.map_grp_pid, how="anti"
        )
        if not missed_rows.is_empty() and not miss_ok:
            raise ValueError(
                f"在映射{self.need_fields}过程中，有未命中规则的数据({missed_rows.height} 行)"
            )

        final_result = self.input_df.join(self.mapped_best_df, on=self.map_grp_pid, how="left")
        for field in self.need_fields:
            field_values = (
                final_result.select(pl.col(field).drop_nulls().unique()).to_series().to_list()
            )
            if any("var{" in str(value) or "exp{" in str(value) for value in field_values):
                return_dtype = self._dynamic_value_dtype(field_values, final_result.schema)
                dynamic_columns = self._dynamic_value_columns(
                    field, field_values, final_result.columns
                )
                calculated_values = [
                    self.apply_value(row, field)
                    for row in final_result.select(dynamic_columns).iter_rows(named=True)
                ]
                final_result = final_result.with_columns(
                    self._dynamic_value_series(field, calculated_values, return_dtype)
                )
        result = final_result.sort(self.input_pid).drop(
            [column for column in drop_columns if column in final_result.columns]
        )
        logger.info(
            "多条件映射完成：规则类型 {} 个，输入 {} 行，输出 {} 行，未命中 {} 行。",
            len(self.mapping_rules),
            self.input_df.height,
            result.height,
            missed_rows.height,
        )
        return result
