# knowlege_segment_builder_by_dify.fill_uncovered_segments_in_chunk

## 描述
在单个硬分页窗口内补齐 Dify 分段结果遗漏的页码，保证后续 segment index 生成覆盖整个窗口。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| segments | List[Dict]\|None | 是 | 已经过硬窗口归一化的 Dify 分段结果 |
| hard_chunk | Dict | 是 | 当前硬窗口，格式为 `{"pages": [start, end]}` |

## Outputs

| 类型 | 说明 |
|------|------|
| List[Dict] | 原有效分段 + 未覆盖页码的固定兜底分段，按起止页排序 |

## 逻辑

1. 将输入 segment 页码再次限制在 `hard_chunk` 内。
2. 统计已覆盖页码。
3. 对未覆盖的连续页码区间调用 `fallback_page_segments`，默认每 10 页生成一个兜底段。
4. 合并原有效分段与兜底段，按页码排序返回。

## SQL

No SQL access.
