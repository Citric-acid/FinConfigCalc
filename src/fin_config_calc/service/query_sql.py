from pathlib import Path

from fin_config_calc.utils.io_dataframe import write_dataframe
from fin_config_calc.utils.io_parquet_sql import query_parquet_by_sql


def query_sql(
    sql: str,
    output_file_path: str | Path,
) -> Path:
    """执行 SQL 查询 Parquet 文件并将结果输出到文件。

    功能：
        调用 Polars SQL 引擎执行查询，再将结果写入指定位置。

    输入数据：
        sql: Polars SQL 查询语句，通过 ``read_parquet('文件路径')`` 引用 Parquet 文件。
        output_file_path: 输出文件路径，支持 ``.xlsx`` 和 ``.parquet``。

    输出结果：
        输出文件的 Path 对象。
    """
    result = query_parquet_by_sql(sql)
    return write_dataframe(result, output_file_path)
