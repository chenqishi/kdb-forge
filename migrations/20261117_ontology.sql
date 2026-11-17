CREATE TABLE IF NOT EXISTS `dops_ontology` (
  `id`           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '物理主键；数据库级唯一的行标识',
  `ontology_id`  CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '对外稳定ID（UUID4 hex）',
  `client`       VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '客户编码；空串=公用',
  `product`      VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '行业/产品线编码；空串=不限',
  `name`         VARCHAR(255) NOT NULL COMMENT '本体名称，投影自 data_json；参与业务键判重',
  `alias_name`   JSON NOT NULL COMMENT '别名数组，投影自 data_json',
  `description`  VARCHAR(2048) NOT NULL DEFAULT '' COMMENT '一句话说明，投影自 data_json',
  `data_json`    JSON NOT NULL COMMENT '完整本体文档',
  `status`       VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'draft/active；只有 active 参与 resolve',
  `revision`     INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '乐观锁版本，每次写+1',
  `create_time`  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `update_time`  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  `del_flag`     TINYINT NOT NULL DEFAULT 0 COMMENT '0正常；1已删',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ontology_id` (`ontology_id`),
  KEY `idx_scope_name` (`client`,`product`,`name`,`del_flag`),
  KEY `idx_scope_status` (`client`,`product`,`status`,`del_flag`),
  KEY `idx_update_time` (`update_time`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='客户业务本体（一行=一套完整本体）';
