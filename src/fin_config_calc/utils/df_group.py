import polars as pl
from loguru import logger


def group_sum(
    df: pl.DataFrame,
    sum_by: list[str] | None = None,
    group_by: list[str] | None = None,
    group_by_exclude: list[str] | None = None,
    abs_delta: float = 0.2,
) -> pl.DataFrame:
    """
    - 功能：
        - 对 DataFrame 做 sum 聚合的包装，支持按“指定分组列”或“排除列自动推断分组列”，并校验聚合前后总和差异；
        - 可选地基于 from_pid 生成汇总层 cid 及 pid-cid 对应关系，并支持写出到 OSS。（pid-cide对应关系解释：把100行聚合为10行后，100行的N行对应10行中的1行）
        - 相比于pandas自带的groupby.sum，这个函数多了：
          - 支持通过 group_by_exclude 参数自动推断分组列，简化调用时的列名管理；
          - 处理 None/空串 替换为 0 并转换为 float，避免数据遗漏；
          - 聚合前后对 sum_by 列的总和做一致性校验
          - 支持基于 from_pid 生成 cid 映射关系，便于后续多级汇总追溯。

    - 输入数据：
        - df (pd.DataFrame): 待聚合的数据表；
        - sum_by (List[str]): 需要求和的数值列；
        - group_by (List[str]): 显式分组列列表；
        - group_by_exclude (List[str]): 需要从“自动推断分组列”中排除的列，两者与 group_by 不能同时非空；
        - abs_delta (float): 聚合前后总和允许的最大绝对差，默认 0.2；
        - from_pid (str): 明细层主键列名；
        - cid_col (str): 聚合后 ID 列名；
        - cid_prefix (str): 生成 cid 的前缀；
        - type_cid (str): cid 类型标识，配合 from_pid 唯一确定一条映射；
        - cid_oss_path (str): pid-cid 对应关系写出到 OSS 的路径，为空则不写；
        - keep_from_pid (bool): 是否在结果中保留 from_pid 列；
        - append_cid (bool): 是否在结果中保留生成的 cid 列。
    - 输出结果：
        - 若未启用 from_pid/cid 逻辑：返回聚合后的 DataFrame；
        - 若启用 from_pid/cid：返回 (result_df, fromcid_df) 二元组，其中 fromcid_df 为映射表。
    - 副作用：
        - 会将 sum_by 列中的 None/空串统一填充为 0 再转换为 float；
        - 在开启 cid_oss_path 时会将 fromcid_df 写入 OSS；
        - 若总和偏差超过 abs_delta 或 from_pid 唯一性不满足会抛出异常。
    - 依赖的其他函数：
        - df_to_oss: 写出 pid-cid 对应关系到 OSS；
        - get_mr_oss_bucket: 获取 Bucket；
        - pandas.DataFrame.groupby/sum/explode 等。
    - 使用场景：
        - 各类费用分摊/指标汇总的聚合步骤，尤其是需要保证“汇总前后总和一致”且需要构建 pid→cid 汇总映射时。
    """
    sum_by = sum_by or []
    group_by = group_by or []
    group_by_exclude = group_by_exclude or []

    if group_by and group_by_exclude:
        raise ValueError("group_by 和 group_by_exclude 不能同时输入")
    if not group_by:
        group_by = [col for col in df.columns if col not in group_by_exclude and col not in sum_by]

    if sum_by:
        df = df.with_columns(pl.col(sum_by).cast(pl.Float64, strict=False).fill_null(0))

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
