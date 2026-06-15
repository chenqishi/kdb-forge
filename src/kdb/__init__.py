"""kdb —— Knowledge Database Builder（重构版）。

重构第一步：把知识库增删改查（CRUD）抽取成高内聚低耦合的独立模块。
- crud.repository.KnowledgeRepository：纯向量 CRUD（封装并复用旧 EsSearchInterface）
- crud.service.KnowledgeService：文本级 CRUD（注入 embedding 客户端）
"""

__version__ = "0.1.0"
