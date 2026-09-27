import polars as pl
from loguru import logger

from fin_config_calc.utils.df_numeric import cast_numeric_columns


def group_sum(
    df: pl.DataFrame,
    sum_by: list[str] | None = None,
    group_by: list[str] | None = None,
    group_by_exclude: list[str] | None = None,
    abs_delta: float = 0.2,
) -> pl.DataFrame:
    """按维度汇总数值列，并校验汇总前后的金额总和。

    Args:
        df: 待汇总的 Polars DataFrame。
        sum_by: 要求和的数值列；为空时不执行数值聚合。
        group_by: 分组列；为空时从非金额列中推断。
        group_by_exclude: 自动推断分组列时排除的列，不能与 ``group_by`` 同时指定。
        abs_delta: 汇总前后总和允许的绝对差值。

    Returns:
        汇总后的新 DataFrame。金额空值和空字符串按零处理；无法转换的非空值及
        NaN/正负无穷会抛出 ``ValueError``。
    """
    sum_by = sum_by or []
    group_by = group_by or []
    group_by_exclude = group_by_exclude or []

    if group_by and group_by_exclude:
        raise ValueError("group_by 和 group_by_exclude 不能同时输入")
    if not group_by:
        group_by = [col for col in df.columns if col not in group_by_exclude and col not in sum_by]

    if sum_by:
        df = cast_numeric_columns(df, sum_by, "汇总表")

    if not group_by:
        group_by = [col for col in df.columns if col not in sum_by]

    if sum_by:
        result = df.group_by(group_by).agg(pl.col(sum_by).sum())
    else:
        result = df.select(group_by).unique(maintain_order=True)

    if sum_by:
        sum_list_before = df.select(pl.col(sum_by).sum()).sum_horizontal().item()
        sum_list_after = result.select(pl.col(sum_by).sum()).sum_horizontal().item()
        if abs(sum_list_before - sum_list_after) > abs_delta:
            raise ValueError(
                f"分组聚合后的sum_list数据之和 {sum_list_before} != 分组聚合之前的sum_list数据之和 {sum_list_after}"
            )

    logger.info(
        "分组聚合完成：分组字段={}，汇总字段={}，输入 {} 行，输出 {} 行。",
        group_by,
        sum_by,
        df.height,
        result.height,
    )
    return result
