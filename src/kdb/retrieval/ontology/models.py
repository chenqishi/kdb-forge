"""src/kdb/retrieval/ontology/models.py —— 文档结构真值，Pydantic v2，Python 3.9 兼容。"""
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

DATA_TYPES = ("string", "integer", "number", "boolean", "date", "datetime", "enum", "object", "array")
ITEM_TYPES = ("string", "integer", "number", "boolean", "date", "datetime", "object", "enum")
CARDINALITIES = ("1:1", "1:N", "N:1", "N:M")
SEVERITIES = ("hard", "soft")

# 用 Literal 而不是 str + validator：生成的 JSON Schema 会直接带 enum/const，
# 结构约束只在一处维护。DATA_TYPES 等元组供 /ontology_meta 与校验复用。
DataType = Literal["string", "integer", "number", "boolean", "date", "datetime", "enum", "object", "array"]
ItemType = Literal["string", "integer", "number", "boolean", "date", "datetime", "object", "enum"]
Cardinality = Literal["1:1", "1:N", "N:1", "N:M"]
Severity = Literal["hard", "soft"]

# 别名 1–128 字符；样例文本 ≤512 字符；列表长度由各字段的 max_length 控制
AliasStr = Annotated[str, Field(min_length=1, max_length=128)]
AliasList = List[AliasStr]
ExampleList = List[Annotated[str, Field(max_length=512)]]

class _Node(BaseModel):
    # extra=forbid 让未知键直接失败；str_strip_whitespace 承担 3.4 第 1 步
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

class Attribute(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=512)
    data_type: DataType
    required: bool = False
    unique: bool = False
    value_set: Optional[str] = Field(default=None, max_length=128)
    ref: Optional[str] = Field(default=None, max_length=128)
    item_type: Optional[ItemType] = None
    examples: ExampleList = Field(default_factory=list, max_length=20)
    llm_hints: Dict[str, Any] = Field(default_factory=dict)

class ObjectType(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=512)
    definition: str = Field(default="", max_length=2048)
    identity: List[str] = Field(min_length=1, max_length=10)
    attributes: List[Attribute] = Field(min_length=1, max_length=200)
    examples: ExampleList = Field(default_factory=list, max_length=20)
    llm_hints: Dict[str, Any] = Field(default_factory=dict)

class Relation(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=512)
    subject: str = Field(min_length=1, max_length=128)
    predicate: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    object: str = Field(min_length=1, max_length=128)
    cardinality: Cardinality
    join: str = Field(default="", max_length=512)
    examples: ExampleList = Field(default_factory=list, max_length=20)
    llm_hints: Dict[str, Any] = Field(default_factory=dict)

class EnumValue(_Node):
    value: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    label: str = Field(min_length=1, max_length=128)
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=512)

class ValueSet(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=512)
    values: List[EnumValue] = Field(min_length=1, max_length=100)

class Rule(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    description: str = Field(default="", max_length=512)
    condition: str = Field(min_length=1, max_length=4096)
    effect: str = Field(min_length=1, max_length=2048)
    severity: Severity
    applies_to: List[str] = Field(default_factory=list, max_length=20)
    examples: ExampleList = Field(default_factory=list, max_length=20)

class Term(_Node):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^.\x00-\x1f\x7f]+$")
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(min_length=1, max_length=2048)
    refers_to: Optional[str] = Field(default=None, max_length=256)
    examples: ExampleList = Field(default_factory=list, max_length=20)
    llm_hints: Dict[str, Any] = Field(default_factory=dict)

class OntologyDocument(_Node):
    schema_version: Literal["1.0"]
    name: str = Field(min_length=1, max_length=255)
    alias_name: AliasList = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=2048)
    client: str = Field(default="", max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")
    product: str = Field(default="", max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")
    language: str = Field(default="zh-CN", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    definition: str = Field(default="", max_length=4096)
    object_types: List[ObjectType] = Field(min_length=1, max_length=200)
    relations: List[Relation] = Field(default_factory=list, max_length=500)
    value_sets: List[ValueSet] = Field(default_factory=list, max_length=200)
    rules: List[Rule] = Field(default_factory=list, max_length=200)
    terms: List[Term] = Field(default_factory=list, max_length=500)
    examples: ExampleList = Field(default_factory=list, max_length=20)
    llm_hints: Dict[str, Any] = Field(default_factory=dict)
    extensions: Dict[str, Any] = Field(default_factory=dict)

    # schema_version 用 Literal 表达；第 2 步已在进入 Pydantic 前短路掉非 1.0
