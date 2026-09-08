from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl
from loguru import logger


class DataAllocator:
    """按照长表因子权重执行单轮分摊或多轮兜底分摊。

    类本身不保存运行状态，可以复用同一个实例执行多次分摊。以下划线开头的列名
    只用于一次调用中的关联和计算，返回结果前会被删除。
    """

    _in_out_label = "dim_alclabel"
    _trace_label = "分摊线索_family"
    _row_id = "_tmp_allocation_row_id"
    _basic_row_id = "_tmp_allocation_basic_row_id"
    _rate_norm = "_tmp_allocation_rate_norm"

    @staticmethod
    def _as_columns(columns: str | Sequence[str], argument: str) -> list[str]:
        """将单个列名或列名序列统一转换为非空列表。"""
        result = [columns] if isinstance(columns, str) else list(columns)
        if not result:
            raise ValueError(f"{argument} 列表不能为空")
        return result

    @staticmethod
    def _require_columns(df: pl.DataFrame, columns: Sequence[str], table_name: str) -> None:
        """检查 DataFrame 是否包含指定字段，并集中报告缺失字段。"""
        missing = sorted(set(columns) - set(df.columns))
        if missing:
            raise ValueError(f"{table_name}缺少字段: {missing}")

    @staticmethod
    def _filter_valid_keys(df: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
        """过滤任一连接键为 null 或空字符串的记录。"""
        conditions = [
            pl.col(column).is_not_null()
            & (pl.col(column).cast(pl.String, strict=False).fill_null("") != "")
            for column in columns
        ]
        return df.filter(pl.all_horizontal(conditions))

    @staticmethod
    def _group_left(
        df: pl.DataFrame,
        value_columns: list[str],
        group_by: Sequence[str] | None,
        group_by_exclude: Sequence[str] | None,
    ) -> pl.DataFrame:
        """按白名单或黑名单维度预聚合待摊金额列。"""
        explicit_group_by = list(group_by or [])
        excluded = list(group_by_exclude or [])
        if explicit_group_by and excluded:
            raise ValueError("group_by 和 group_by_exclude 不能同时输入")
        if not explicit_group_by and not excluded:
            return df

        grouping_columns = explicit_group_by or [
            column
            for column in df.columns
            if column not in value_columns and column not in excluded
        ]
        if not grouping_columns:
            return df.select(pl.col(value_columns).sum())
        return df.group_by(grouping_columns, maintain_order=True).agg(pl.col(value_columns).sum())

    def allocation_basic(
        self,
        df_left: pl.DataFrame,
        df_rate: pl.DataFrame,
        value_left: str | Sequence[str],
        rate_right: str,
        left_on: Sequence[str],
        right_on: Sequence[str] | None = None,
        replace_right: str | Sequence[str] = (),
        update_column: Mapping[str, Any] | None = None,
        keep_label: bool = False,
        group_by: Sequence[str] | None = None,
        group_by_exclude: Sequence[str] | None = None,
        abs_delta: float = 1,
        calc_rate_col: str = "",
    ) -> pl.DataFrame:
        """执行一轮基于权重的分摊。

        功能：
            将 ``df_left`` 中的一个或多个金额列，按照 ``df_rate`` 中每个连接键
            对应的权重比例分配到 ``replace_right`` 指定的目标维度。返回结果同时
            包含金额取负的分出行和按目标维度展开的分入行。

        输入数据：
            df_left: 待分摊数据。除目标维度被因子表覆盖外，其余字段保留。
            df_rate: 长格式因子表。相同连接键和目标维度的重复权重会先合并。
            value_left: 待分摊金额列名，支持单列名或多列名。
            rate_right: 因子表中的权重列。null、非数值和聚合后为零的权重会排除。
            left_on: 待摊表连接键，不允许为空。
            right_on: 因子表连接键；省略时使用 ``left_on``，字段数量必须一致。
            replace_right: 分入方目标维度。若左表已有同名列，分入行使用因子表值。
            update_column: 最终同时写入分入行和分出行的固定字段。
            keep_label: 是否保留 ``dim_alclabel``，其值为 ``in`` 或 ``out``。
            group_by: 分摊前聚合使用的维度白名单。
            group_by_exclude: 分摊前聚合时排除的维度黑名单，不能与 ``group_by`` 同用。
            abs_delta: 每个金额列允许的分入分出合计绝对误差。
            calc_rate_col: 非空时新增比例列。比例取当前分入行最大金额对应的
                ``分入金额 / 原金额``；分出行该列为 null。

        输出结果：
            返回一个新的 Polars DataFrame。金额列统一转换为 Float64；默认删除
            分入分出标签，且不返回任何内部临时列。

        重要约束：
            因子表必须覆盖左表的全部连接键。某个连接键权重合计为零、字段缺失、
            输入表为空或最终金额不守恒时会抛出 ``ValueError``。
        """
        # 步骤 0：标准化参数并完成结构校验。replace_right 与 right_on 重叠的字段
        # 已由连接键保留，不再作为需要覆盖的目标维度。
        value_columns = self._as_columns(value_left, "value_left")
        left_keys = list(left_on)
        right_keys = list(right_on) if right_on else left_keys.copy()
        target_columns = self._as_columns(replace_right, "replace_right")
        target_columns = [column for column in target_columns if column not in right_keys]
        if not target_columns:
            raise ValueError("replace_right 列表不能为空，且不能仅包含 right_on 字段")
        if not left_keys:
            raise ValueError("allocation_basic 的 left_on 列表不能为空")
        if len(left_keys) != len(right_keys):
            raise ValueError("left_on 和 right_on 元素个数必须相等")
        if df_left.is_empty():
            raise ValueError("左表不能为空")
        if df_rate.is_empty():
            raise ValueError("右表不能为空")

        self._require_columns(df_left, [*value_columns, *left_keys], "左表")
        self._require_columns(df_rate, [rate_right, *right_keys, *target_columns], "因子表")
        reserved_columns = {self._basic_row_id, self._rate_norm}
        conflicting_reserved = reserved_columns & (set(df_left.columns) | set(df_rate.columns))
        if conflicting_reserved:
            raise ValueError(f"输入表不能包含保留字段: {sorted(conflicting_reserved)}")

        # 步骤 1：金额列显式转为 Float64，并按需预聚合左表。临时行号用于把分入行
        # 关联回对应分出行，以便计算 calc_rate_col，返回前会统一删除。
        #
        # 输入 df_left：                         聚合后 left（示意）：
        # +------+-------+--------+             +------+-------+--------+------+
        # | key  | item  | amount |             | key  | item  | amount | _id  |
        # +------+-------+--------+             +------+-------+--------+------+
        # | A    | P1    | 100    |      ->     | A    | P1    | 100.0  | 0    |
        # | B    | P2    | -50    |             | B    | P2    | -50.0  | 1    |
        # +------+-------+--------+             +------+-------+--------+------+
        left = df_left.with_columns(
            pl.col(value_columns).cast(pl.Float64, strict=False).fill_null(0)
        )
        left = self._group_left(left, value_columns, group_by, group_by_exclude)
        self._require_columns(left, left_keys, "聚合后的左表")
        left = left.with_row_index(self._basic_row_id)
        output = left

        # 步骤 2：因子表保持长格式，先合并重复目标，再按 right_on 分组归一化。
        #
        # 输入 df_rate：                         归一化后 rate：
        # +------+--------+--------+             +------+--------+------------+
        # | key  | target | weight |             | key  | target | rate_norm  |
        # +------+--------+--------+             +------+--------+------------+
        # | A    | X      | 1      |             | A    | X      | 0.25       |
        # | A    | Y      | 3      |      ->     | A    | Y      | 0.75       |
        # | B    | X      | 2      |             | B    | X      | 0.50       |
        # | B    | Y      | 2      |             | B    | Y      | 0.50       |
        # +------+--------+--------+             +------+--------+------------+
        rate = (
            df_rate.filter(pl.col(rate_right).is_not_null())
            .with_columns(pl.col(rate_right).cast(pl.Float64, strict=False))
            .filter(pl.col(rate_right).is_not_null())
            .group_by([*right_keys, *target_columns], maintain_order=True)
            .agg(pl.col(rate_right).sum())
            .filter(pl.col(rate_right) != 0)
        )
        denominators = rate.group_by(right_keys).agg(
            pl.col(rate_right).sum().alias("_tmp_allocation_rate_sum")
        )
        zero_denominators = denominators.filter(pl.col("_tmp_allocation_rate_sum") == 0)
        if not zero_denominators.is_empty():
            raise ValueError(
                "因子小数化时分母为 0，请检查分摊因子合理性。"
                f"问题连接键组合（前10行）:\n{zero_denominators.head(10)}"
            )
        rate = (
            rate.join(denominators, on=right_keys, how="left")
            .with_columns(
                (pl.col(rate_right) / pl.col("_tmp_allocation_rate_sum")).alias(self._rate_norm)
            )
            .select([*right_keys, *target_columns, self._rate_norm])
        )

        # 步骤 3：在正式展开前检查因子覆盖范围。anti join 的结果就是“左表存在、
        # 因子表不存在”的连接键；若继续计算，这些记录将无法产生守恒的分入行。
        missing_keys = (
            left.select(left_keys)
            .unique(maintain_order=True)
            .join(
                rate.select(right_keys).unique(),
                left_on=left_keys,
                right_on=right_keys,
                how="anti",
                nulls_equal=True,
            )
        )
        if not missing_keys.is_empty():
            raise ValueError(
                "分摊系数表的索引必须覆盖左表所有索引。"
                f"缺失连接键组合（前10行）:\n{missing_keys.head(10)}"
            )

        # 步骤 4：左表与归一化因子做一对多连接，每条左表记录按命中的目标数展开。
        # 目标维度先改为临时列名，是为了在左表已有同名维度时明确使用因子表值覆盖。
        #
        # 输入 left + rate：                    展开后 joined：
        # +------+--------+                     +------+--------+--------+-----------+
        # | key  | amount |                     | key  | amount | target | rate_norm |
        # +------+--------+                     +------+--------+--------+-----------+
        # | A    | 100.0  |      join ->        | A    | 100.0  | X      | 0.25      |
        # +------+--------+                     | A    | 100.0  | Y      | 0.75      |
        #                                        +------+--------+--------+-----------+
        target_aliases = {
            column: f"_tmp_allocation_target_{index}" for index, column in enumerate(target_columns)
        }
        joined = left.join(
            rate.rename(target_aliases),
            left_on=left_keys,
            right_on=right_keys,
            how="left",
            nulls_equal=True,
        )
        joined = joined.drop(
            [column for column in target_columns if column in joined.columns]
        ).rename({temporary: original for original, temporary in target_aliases.items()})

        # 步骤 5：每个金额列乘以归一化比例，并过滤所有金额均接近零的分入行。
        #
        # +------+--------+--------+-----------+     +------+--------+--------+
        # | key  | amount | target | rate_norm |     | key  | amount | target |
        # +------+--------+--------+-----------+     +------+--------+--------+
        # | A    | 100.0  | X      | 0.25      | ->  | A    | 25.0   | X      |
        # | A    | 100.0  | Y      | 0.75      |     | A    | 75.0   | Y      |
        # +------+--------+--------+-----------+     +------+--------+--------+
        allocated = joined.with_columns(
            [(pl.col(column) * pl.col(self._rate_norm)).alias(column) for column in value_columns]
        ).filter(
            pl.col(self._rate_norm).is_not_null()
            & pl.any_horizontal(
                [pl.col(column).abs().round(10) >= 1e-10 for column in value_columns]
            )
        )
        allocated = allocated.drop(self._rate_norm)

        # 步骤 6：按全部非金额字段汇总分入行。重复因子和重复左表维度展开出的
        # 相同目标会在这里合并；Polars group_by 会保留 null 维度分组。
        dimension_columns = [column for column in allocated.columns if column not in value_columns]
        if dimension_columns:
            allocated = allocated.group_by(dimension_columns, maintain_order=True).agg(
                pl.col(value_columns).sum()
            )

        updates = dict(update_column or {})
        if updates:
            expressions = [pl.lit(value).alias(column) for column, value in updates.items()]
            allocated = allocated.with_columns(expressions)
            output = output.with_columns(expressions)

        # 步骤 7：可选地反算每条分入记录的分摊比例。多金额列时沿用参考实现，
        # 选择该分入行数值最大的金额列作为比例计算基准。
        if calc_rate_col:
            original_values = output.select([self._basic_row_id, *value_columns]).rename(
                {column: f"_tmp_allocation_original_{column}" for column in value_columns}
            )
            maximum_column = "_tmp_allocation_maximum_value"
            allocated = allocated.join(original_values, on=self._basic_row_id, how="left")
            allocated = allocated.with_columns(
                pl.max_horizontal(value_columns).alias(maximum_column)
            ).with_columns(
                pl.coalesce(
                    [
                        pl.when(pl.col(column) == pl.col(maximum_column))
                        .then(pl.col(column) / pl.col(f"_tmp_allocation_original_{column}"))
                        .otherwise(None)
                        for column in value_columns
                    ]
                ).alias(calc_rate_col)
            )
            allocated = allocated.drop(
                [
                    maximum_column,
                    *[f"_tmp_allocation_original_{column}" for column in value_columns],
                ]
            )

        # 步骤 8：生成正数/原符号的分入行和金额取负的分出行，再纵向拼接。
        # diagonal_relaxed 允许 replace_right 或 calc_rate_col 只存在于分入行。
        #
        # 最终结果（keep_label=True）：
        # +------+--------+--------+--------------+
        # | key  | target | amount | dim_alclabel |
        # +------+--------+--------+--------------+
        # | A    | null   | -100.0 | out          |
        # | A    | X      | 25.0   | in           |
        # | A    | Y      | 75.0   | in           |
        # +------+--------+--------+--------------+
        allocated = allocated.with_columns(pl.lit("in").alias(self._in_out_label))
        output = output.with_columns(
            [(-pl.col(column)).alias(column) for column in value_columns]
            + [pl.lit("out").alias(self._in_out_label)]
        )
        result = pl.concat([output, allocated], how="diagonal_relaxed")
        if not keep_label:
            result = result.drop(self._in_out_label)
        result = result.drop(self._basic_row_id)

        imbalance = {
            column: total
            for column in value_columns
            if abs(total := (result.get_column(column).sum() or 0)) > abs_delta
        }
        if imbalance:
            raise ValueError(
                f"分摊结果中，分入金额 + 分出金额必须等于 0；当前合计金额: {imbalance}"
            )
        logger.info(
            "基础分摊完成：连接字段={}，金额字段={}，输入 {} 行，输出 {} 行。",
            left_keys,
            value_columns,
            df_left.height,
            result.height,
        )
        return result

    def allocation_family(
        self,
        df_left: pl.DataFrame,
        df_rate: pl.DataFrame,
        value_left: str | Sequence[str],
        rate_right: str,
        allocation_list: Sequence[Mapping[str, Any]],
        update_column: Mapping[str, Any] | None = None,
        keep_label: bool = False,
        group_by: Sequence[str] | None = None,
        group_by_exclude: Sequence[str] | None = None,
        abs_delta: float = 5,
        calc_rate_col: str = "",
        miss_ok: bool | None = None,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """按规则顺序执行多轮兜底分摊。

        功能：
            按 ``allocation_list`` 顺序处理待摊数据。每轮只选择“尚未分摊、连接键
            非空且能命中当前因子表”的原始行；一旦某行在较精细规则中命中，后续
            较粗规则不会再次处理。每轮实际金额计算由 ``allocation_basic`` 完成。

        输入数据：
            df_left: 全部待分摊数据。
            df_rate: 各轮共同使用的长格式因子表。
            value_left、rate_right、update_column、keep_label、group_by、
                group_by_exclude、abs_delta、calc_rate_col: 含义与
                ``allocation_basic`` 相同。
            allocation_list: 有序规则列表。每条规则包含 ``left_on``、可选的
                ``right_on`` 和 ``replace_right``。空 ``left_on`` 表示不分组的大摊。
            miss_ok: 为 ``False`` 时，只要存在未分摊记录就抛出 ``ValueError``；
                ``True`` 或 ``None`` 时在第二个返回值中返回这些记录。

        输出结果：
            二元组 ``(result, missing)``。``result`` 是各轮分摊结果的纵向合并；
            ``missing`` 保持原始字段和值，不包含任何内部行号。

        规则命中示例：
            假设原始数据依次为 ``(A, A1)``、``(A, null)``、``(B, B1)``：

            +------+---------------------+----------------------------+
            | 轮次 | left_on             | 本轮处理                   |
            +------+---------------------+----------------------------+
            | 1    | [level_1, level_2]  | (A, A1)，精细键优先命中   |
            | 2    | [level_1]           | (A, null)，按一级维度兜底  |
            +------+---------------------+----------------------------+

            ``(B, B1)`` 若两轮均无对应因子，则进入 ``missing``。内部临时行号只用来
            识别“原始行是否已处理”，不是业务 pid/cid，也不会出现在返回结果中。
        """
        if self._row_id in df_left.columns:
            raise ValueError(f"左表不能包含保留字段 {self._row_id!r}")
        value_columns = self._as_columns(value_left, "value_left")
        left = df_left.with_row_index(self._row_id)
        allocated_ids: set[int] = set()
        results: list[pl.DataFrame] = []

        # 每轮都从尚未分摊的原始行开始筛选。规则顺序即优先级：列表越靠前，
        # 连接条件通常越精细；已经命中的行不会流入后续兜底规则。
        for index, allocation in enumerate(allocation_list):
            left_keys = list(allocation["left_on"])
            right_keys = list(allocation.get("right_on") or left_keys)
            target_columns = self._as_columns(allocation["replace_right"], "replace_right")
            if len(left_keys) != len(right_keys):
                raise ValueError("left_on 和 right_on 元素个数必须相等")

            candidates = left.filter(~pl.col(self._row_id).is_in(allocated_ids))
            current_rate = df_rate
            temporary_key: str | None = None
            if not left_keys:
                # 空连接键表示“大摊”：两侧增加同一个常量键，使所有候选行都能
                # 与本轮全部因子目标连接。临时键随本轮结果一并在最终阶段删除。
                temporary_key = f"_tmp_allocation_join_{index}"
                candidates = candidates.with_columns(pl.lit(1).alias(temporary_key))
                current_rate = current_rate.with_columns(pl.lit(1).alias(temporary_key))
                left_keys = right_keys = [temporary_key]
            else:
                self._require_columns(candidates, left_keys, "左表")
                self._require_columns(current_rate, right_keys, "因子表")
                candidates = self._filter_valid_keys(candidates, left_keys)
                current_rate = self._filter_valid_keys(current_rate, right_keys)

            if candidates.is_empty() or current_rate.is_empty():
                continue

            # inner join 只确定本轮能够分摊的原始行号，不在这里展开金额；这样可以
            # 先精确记录已分摊集合，再把选中的完整数据交给 allocation_basic。
            matched_ids = (
                candidates.select([self._row_id, *left_keys])
                .join(
                    current_rate.select(right_keys).unique(),
                    left_on=left_keys,
                    right_on=right_keys,
                    how="inner",
                )
                .get_column(self._row_id)
                .to_list()
            )
            if not matched_ids:
                continue
            to_allocate = candidates.filter(pl.col(self._row_id).is_in(matched_ids))
            updates = dict(update_column or {})
            updates[self._trace_label] = f"[自动]家族式分摊_次序{index + 1}, 分摊范围: {left_keys}"
            result = self.allocation_basic(
                df_left=to_allocate,
                df_rate=current_rate,
                value_left=value_columns,
                rate_right=rate_right,
                left_on=left_keys,
                right_on=right_keys,
                replace_right=target_columns,
                update_column=updates,
                keep_label=keep_label,
                group_by=group_by,
                group_by_exclude=group_by_exclude,
                abs_delta=abs_delta,
                calc_rate_col=calc_rate_col,
            )
            if temporary_key is not None:
                result = result.drop(temporary_key)
            results.append(result)
            allocated_ids.update(matched_ids)

        # 所有规则执行完后，仍未进入 allocated_ids 的原始行即为未分摊数据。
        missing = left.filter(~pl.col(self._row_id).is_in(allocated_ids)).drop(self._row_id)
        if not missing.is_empty() and miss_ok is False:
            raise ValueError(f"有数据未被分摊: {allocation_list}")

        if results:
            result = pl.concat(results, how="diagonal_relaxed")
        else:
            # 即使没有任何规则命中，也补齐规则声明的目标列，让空结果具有可预期
            # 的结构，调用方无需针对“零命中”单独推断 schema。
            result = left.head(0)
            for allocation in allocation_list:
                for column in self._as_columns(allocation["replace_right"], "replace_right"):
                    if column not in result.columns:
                        result = result.with_columns(pl.lit(None).alias(column))
        result = result.drop(self._row_id, strict=False)
        if not keep_label:
            result = result.drop(self._trace_label, strict=False)
        logger.info(
            "家族式分摊完成：规则 {} 轮，输入 {} 行，已分摊 {} 行，未分摊 {} 行，输出 {} 行。",
            len(allocation_list),
            df_left.height,
            len(allocated_ids),
            missing.height,
            result.height,
        )
        return result, missing
