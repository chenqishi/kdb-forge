# private_value

private_value(key) -> str：在原字面量求值位置读取私有默认值，首次从本项目private/runtime_config/hardcoded_defaults.json加载并缓存。
有效值与私有快照逐项对照；不访问线上、不更换/轮换凭据。私有文件缺失/缺字段会显式失败，不能用空字符串或占位符替代。
这是r1要求的必要凭据外置变更；配置原有外部覆盖和客户选择不变。无SQL/ES。
