from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
import difflib
import pandas as pd

def diff_excel(file1_path: str, file2_path: str, columns: Tuple[int, int], output_file: str = None) -> None:
    """
    比较两个Excel文件中指定列的差异
    
    Args:
        file1_path: 第一个Excel文件路径
        file2_path: 第二个Excel文件路径
        columns: 需要比较的列号元组 (file1的列号, file2的列号)
        output_file: 输出结果的Excel文件路径，如果不指定则只输出到终端
    """
    # 读取两个Excel文件
    excel1 = pd.ExcelFile(file1_path)
    excel2 = pd.ExcelFile(file2_path)

    # 获取两个文件共同的sheet名称
    common_sheets = set(excel1.sheet_names).intersection(set(excel2.sheet_names))

    # 用于存储差异结果的列表
    diff_results: List[Dict[str, Any]] = []

    # 用于统计总行数
    total_rows_file1 = 0
    total_rows_file2 = 0

    col1, col2 = columns

    for sheet_name in common_sheets:
        df1 = pd.read_excel(file1_path, sheet_name=sheet_name)
        df2 = pd.read_excel(file2_path, sheet_name=sheet_name)

        # 累加总行数
        total_rows_file1 += len(df1)
        total_rows_file2 += len(df2)

        # 检查列号是否有效
        if col1 >= len(df1.columns):
            print(f"警告：在Sheet 1中 {sheet_name}中列号无效")
            continue
        if col2 >= len(df2.columns):
            print(f"警告：在Sheet 2中 {sheet_name}中列号无效")
            continue

        print(f"\n比较Sheet: {sheet_name}")

        for row in range(min(len(df1), len(df2))):
            # 获取单元格内容
            cell1 = str(df1.iloc[row, col1]) if not pd.isna(df1.iloc[row, col1]) else ""
            cell2 = str(df2.iloc[row, col2]) if not pd.isna(df2.iloc[row, col2]) else ""

            # 获取两个文件的第一列内容
            first_col1 = str(df1.iloc[row, 0]) if not pd.isna(df1.iloc[row, 0]) else ""
            first_col2 = str(df2.iloc[row, 0]) if not pd.isna(df2.iloc[row, 0]) else ""

            # 如果内容不同，计算差异
            if cell1 != cell2:
                # 使用difflib计算具体的文本差异
                differ = difflib.Differ()
                diff = list(differ.compare(cell1.split(), cell2.split()))

                removed = []
                added = []

                for d in diff:
                    if d.startswith('- '):
                        removed.append(d[2:])
                    elif d.startswith('+ '):
                        added.append(d[2:])

                removed_str = ' '.join(removed)
                added_str = ' '.join(added)

                diff_line = f"少：{{{removed_str}}},多：{{{added_str}}}"
                print(f"{sheet_name}\t{row+1}\t{diff_line}")

                # 将差异结果添加到列表中，包含两个文件的第一列内容
                diff_results.append({
                    'Sheet名称': sheet_name,
                    '行号': row + 1,
                    '原始问题': first_col1,
                    '修改问题(部分可能不会改)': first_col2,
                    '原始内容': cell1,
                    '新内容': cell2,
                    '差异描述': diff_line
                })

        # 检查行数差异
        if len(df1) != len(df2):
            diff_msg = f"\n行数差异 - {sheet_name}:\n文件1行数: {len(df1)}\n文件2行数: {len(df2)}"
            print(diff_msg)
            diff_results.append({
                'Sheet名称': sheet_name,
                '行号': '',
                '原始问题': '',
                '修改问题(部分可能不会改)': '',
                '原始内容': '',
                '新内容': '',
                '差异描述': f"行数差异 - 文件1: {len(df1)}行, 文件2: {len(df2)}行"
            })

    # 输出总行数对比
    print("\n=== 总行数对比 ===")
    print(f"文件1总行数: {total_rows_file1}")
    print(f"文件2总行数: {total_rows_file2}")
    print(f"行数差异: {abs(total_rows_file1 - total_rows_file2)}")

    # 如果指定了输出文件，将结果写入Excel
    if output_file and diff_results:
        df_result = pd.DataFrame(diff_results)
        # 调整列的顺序
        columns_order = ['Sheet名称', '行号', '原始问题', '修改问题(部分可能不会改)',
                        '原始内容', '新内容', '差异描述']
        df_result = df_result[columns_order]
        df_result.to_excel(output_file, index=False)
        print(f"\n差异结果已保存到: {output_file}")
