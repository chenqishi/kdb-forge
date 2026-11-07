import pandas as pd
from collections import Counter
from typing import Dict, List
import logging
import sys

def csv_stat(data_file: str, column_name: str, stat_type='nomluti') -> tuple[Dict[str, int], int]:
    """
    统计CSV文件中指定列的值出现次数，支持一个单元格中包含多个逗号分隔的值
    
    Args:
        data_file (str): CSV文件路径
        column_name (str): 要统计的列名
        stat_type (str): 统计类型，'nomluti' 只统计第一个值，其他统计所有值
    
    Returns:
        tuple[Dict[str, int], int]: (值及其出现次数的字典, 总行数)
    """
    # 读取CSV文件
    df = pd.read_csv(data_file)
    
    # 确保列名存在
    if column_name not in df.columns:
        raise ValueError(f"列名 '{column_name}' 不存在于CSV文件中")
    
    # 获取总行数（不包括空值）
    total_rows = df[column_name].dropna().shape[0]
    
    # 获取指定列的所有值
    values = []
    for cell in df[column_name].dropna():
        # 将单元格中的值按逗号分割，并去除空白
        if stat_type == 'nomluti':
            cell_values = list(sorted([v.strip() for v in str(cell).split(',') if v.strip()], reverse=True))
            cell_values = cell_values[0: 1]
        else:
            cell_values = [v.strip() for v in str(cell).split(',') if v.strip()]
        values.extend(cell_values)
    
    # 使用Counter统计每个值的出现次数
    value_counts = Counter(values)
    
    # 将Counter转换为字典并返回，同时返回总行数
    return dict(value_counts), total_rows

def print_stat_results(stat_results: Dict[str, int], total_rows: int):
    """
    打印统计结果，包含数量和比例，按值的字典序排序
    
    Args:
        stat_results (Dict[str, int]): 统计结果字典
        total_rows (int): 总行数
    """
    print("\n统计结果:")
    print("-" * 60)
    print(f"{'值':<30} {'数量':<10} {'比例':<10}")
    print("-" * 60)
    for value, count in sorted(stat_results.items(), key=lambda x: x[0]):
        percentage = (count / total_rows) * 100
        print(f"{value:<30} {count:<10} {percentage:.2f}%")
    print("-" * 60)
    print(f"总行数: {total_rows}")

def output_csv_stat(data_file: str, column_name: str, stat_type='nomluti'):
    stat_results, total_rows = csv_stat(data_file, column_name, stat_type)
    print_stat_results(stat_results, total_rows)

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'output_csv_stat': output_csv_stat,
    })
    