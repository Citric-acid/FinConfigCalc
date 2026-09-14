import polars as pl
from loguru import logger


def query_parquet_by_sql(sql: str) -> pl.DataFrame:
    """使用 Polars 内置 SQL 引擎查询 Parquet 文件。

    功能：
        执行一条 SQL 语句并返回查询结果。SQL 中通过
        ``read_parquet('文件路径')`` 表函数引用 Parquet 文件。

    输入数据：
        sql: Polars SQL 方言的查询语句，例如
            ``SELECT * FROM read_parquet('d:/data/a.parquet') WHERE amount > 0``。

    输出结果：
        查询结果对应的 Polars DataFrame。

    使用限制：
        路径建议使用正斜杠 ``/``；SQL 方言以 Polars SQL 支持范围为准。
    """
    if not sql or not sql.strip():
        raise ValueError("SQL 语句不能为空")

    dataframe = pl.sql(sql).collect()
    logger.info(
        "SQL 查询完成：共 {} 行、{} 列。",
        dataframe.height,
        dataframe.width,
    )
    return dataframe
