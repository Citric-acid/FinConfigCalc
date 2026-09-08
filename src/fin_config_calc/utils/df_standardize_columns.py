import polars as pl
from loguru import logger

FIELD_NAME_TARGET = "standard"
FIELD_DTYPE_TARGET = "dtype"


def _convert_series_by_dtype(series: pl.Series, dtype_str: str, col_name: str) -> pl.Series:
    """根据规则表中声明的 dtype 对单个 Series 做类型转换。

    - 功能：
        - 按规则表中给定的目标数据类型，将单列数据转换为标准化的 Polars dtype。
    - 输入数据：
        - series (pl.Series): 待转换的数据列（已完成列名映射后的列）。
        - dtype_str (str): 规则表中填写的目标数据类型字符串（不区分大小写，前后空格忽略）。
        - col_name (str): 当前列在标准列中的列名（用于报错信息）。
    - 输出结果：
        - pl.Series: 按 dtype_str 转换后的新 Series。
    - 说明：
        - 若 dtype_str 未在支持列表中，直接抛出 ValueError，不做容错。
        - 支持的取值（不区分大小写，前后空格忽略）：
            * float:     float, float64, double
            * string:    str, string
        - 值级别的转换异常（如无法转为数字）使用 Polars 的非严格转换处理，非法值会被转为 null。
    """

    dtype_str_norm = str(dtype_str).strip().lower()
    if dtype_str_norm == "float":
        normalized = series
        if normalized.dtype == pl.String:
            normalized = normalized.str.strip_chars()
            empty_mask = (normalized == "").fill_null(False)
            normalized = normalized.set(empty_mask, None)

        converted = normalized.cast(pl.Float64, strict=False)

        bad_values = (
            normalized.filter(normalized.is_not_null() & converted.is_null())
            .cast(pl.Utf8)
            .unique()
            .head(20)
            .to_list()
        )
        if bad_values:
            raise ValueError(
                f"规则表中列[{col_name}]存在无法转换为 float 的值："
                f"{bad_values}。请检查并修正后重试。"
            )

        return converted

    if dtype_str_norm == "string":
        return series.cast(pl.Utf8)

    # 未知数据类型，直接报错，不做容错
    raise ValueError(
        f"规则表中列[{col_name}]指定了不支持的数据类型[{dtype_str}]，仅支持 float 和 string，请修改后重试。"
    )


def standardize_columns_by_rules(
    df: pl.DataFrame, df_rule_convert: pl.DataFrame, field_name: str
) -> pl.DataFrame:
    """将输入数据框的列名映射到预定义的标准列名，并按规则表对字段类型做标准化。

    - 功能：
        - 将原始数据 df 的列名依据规则表映射为统一的“标准列名”集合，便于后续合并多个数据源；
        - 若规则表中存在 dtype 列，则对标准列按声明的 dtype 做统一的数据类型转换。

    - 输入数据：
        - df (pl.DataFrame): 待处理的原始数据框；
        - df_rule_convert (pl.DataFrame): 描述列名映射关系和目标数据类型的规则表；
        - field_name (str): 规则表中表示“原始列名”的字段名（例如 "field_name"、"source_col" 等）。

      规则表中可选列（字段名由调用方自己设计，只要与参数一致即可）：
        - standard_col    : 标准列名（由 ``FIELD_NAME_TARGET`` 指向）；
        - field_name   : 原始列名，即需要被转换名称的字段名；
        - dtype : （可选）标准列的目标数据类型列名（由 ``FIELD_DTYPE_TARGET`` 指向）；
                         该列的取值将传入 _convert_series_by_dtype 做强类型转换。

    - 输出结果：
        - pl.DataFrame:
            - 列名已根据规则表完成重命名，且按 df_target 的顺序重新排列；
            - 若规则表中声明了 dtype_target，对应标准列会按照 dtype_target 中的取值做类型标准化；
            - 对于规则表中存在但原始 df 中缺失的标准列，会自动新增并填充 NA。

    - 副作用：
        - 不修改原始 df，只返回新构造的 df_new；
        - 使用 loguru.logger 输出以下信息：
            - 未出现在映射关系中的原始列（unmapped_columns）；
            - 规则表中存在但 df_new 中缺失，需要被强行构造的标准列（missing_columns）。

    - 依赖的其他函数：
        - DataFrame.drop_nulls / DataFrame.select / DataFrame.with_columns 等；
        - _convert_series_by_dtype：负责按照 dtype_target 做单列数据类型转换。

    - 使用场景：
        - 使用频率很高。场景包括：
            - 各种来源的宽表字段名不一致，需要在入仓/汇总前统一成同一批“标准字段名”和类型；
            - 后续合并多张同结构表时，希望列集合和类型对齐，减少额外的清洗逻辑。

        - 示例：
            - 原始字段 a、b1、d2 分别映射为 A、B、D；若规则中定义了 C，但原始数据缺失，则新增列并填充缺失值；
            - 同时通过 dtype_target 列声明目标类型，例如 A 列是 float，B/C/D 为 string。
            - 规则表示意：
                +-----------+------------+--------------+
                | df_target | field_name | dtype_target |
                +===========+============+==============+
                | A         | a          | float        |
                +-----------+------------+--------------+
                | B         | b1         | string       |
                +-----------+------------+--------------+
                | C         | nan        | string       |
                +-----------+------------+--------------+
                | D         | d2         | string       |
                +-----------+------------+--------------+

    - 说明：
        - 若规则表中 df_target（由 ``FIELD_NAME_TARGET`` 指向）存在重复值，会直接抛出异常，避免生成歧义列名；
        - 若规则表中 field_name 列包含 df 中不存在的列名，同样会抛出异常，提醒检查映射关系；
        - 若存在 dtype_target 列，且其中某个取值为不支持的数据类型，会在 _convert_series_by_dtype 中直接抛出 ValueError，
          需要修改规则表后重试，不做静默降级或忽略处理。

    """

    df_cleaned = df_rule_convert.drop_nulls(field_name)

    # 校验：转化规则表中不能有重复字段。改为可以重复，2024年9月5日16:37
    # if df_cleaned[field_name].is_duplicated().any():
    #     raise ValueError("映射表中[{0}]列存在重复值，请检查规则表参数".format(field_name))

    df_target_notnull = df_rule_convert.drop_nulls(FIELD_NAME_TARGET)
    if df_target_notnull.get_column(FIELD_NAME_TARGET).n_unique() != df_target_notnull.height:
        raise ValueError(f"映射表中[{FIELD_NAME_TARGET}]列存在重复值，请检查规则表参数")

    # 校验：转化规则表中的列名必须是真实存在的
    list_not_in_cols = [
        one for one in df_cleaned.get_column(field_name).to_list() if one not in df.columns
    ]
    if len(list_not_in_cols) > 0:
        raise ValueError(
            f"映射表中[{field_name}]列存在的元素{list_not_in_cols}本身不存在于[{field_name}]的列头，"
            "请检查规则表参数"
        )

    df_rule_convert_filtered = df_rule_convert.filter(
        pl.col(FIELD_NAME_TARGET).is_not_null() & pl.col(field_name).is_not_null()
    )  # 标准列名不为空

    mapping_dict = dict(
        zip(
            df_rule_convert_filtered.get_column(field_name).to_list(),
            df_rule_convert_filtered.get_column(FIELD_NAME_TARGET).to_list(),
        )
    )  # 字段名映射关系字典

    # 重命名并删除不需要的列
    df_new = df.select(
        [pl.col(old_name).alias(new_name) for old_name, new_name in mapping_dict.items()]
    )

    # 打印没有映射的列。没有出现在filed_name列的元素，就不会被映射
    unmapped_columns = [c for c in df.columns if c not in mapping_dict]
    if len(unmapped_columns) > 0:
        logger.info("以下列没有映射到标准列名：" + str(unmapped_columns))

    # 对齐字段数。df1 不存在但是标准列名存在的列，就构造列 并且填充为空值
    df_st = df_rule_convert.drop_nulls(FIELD_NAME_TARGET).get_column(FIELD_NAME_TARGET)
    missing_columns = [c for c in df_st.to_list() if c not in df_new.columns]
    for c in missing_columns:
        df_new = df_new.with_columns(pl.lit(None).alias(c))

    if len(missing_columns) > 0:
        logger.info("以下列强行生成：" + str(missing_columns))

    # === 2026年1月25日新增：按照规则表中的 dtype 列做数据类型标准化（若存在） ===
    if FIELD_DTYPE_TARGET in df_rule_convert.columns:
        df_type_rules = df_rule_convert.drop_nulls([FIELD_NAME_TARGET, FIELD_DTYPE_TARGET])
        dtype_mapping = dict(
            zip(df_type_rules[FIELD_NAME_TARGET], df_type_rules[FIELD_DTYPE_TARGET])
        )

        for col_name, dtype_str in dtype_mapping.items():
            if col_name in df_new.columns:
                converted_series = _convert_series_by_dtype(
                    df_new.get_column(col_name), dtype_str, col_name
                )
                df_new = df_new.with_columns(converted_series.alias(col_name))

    # 对字段顺序排序
    order_list = df_target_notnull.get_column(FIELD_NAME_TARGET).to_list()
    result = df_new.select(order_list)
    logger.info(
        "字段标准化完成：输入 {} 行、{} 列，输出 {} 行、{} 列。",
        df.height,
        df.width,
        result.height,
        result.width,
    )
    return result
