"""kdb.modify —— 按已决策计划写入 ES（纯数据，零 LLM）。"""

from kdb.modify.models import InsertItem, ModifyPlan, ModifyResult, UpdateItem
from kdb.modify.service import apply_modify_plan

__all__ = ["ModifyPlan", "UpdateItem", "InsertItem", "ModifyResult", "apply_modify_plan"]
