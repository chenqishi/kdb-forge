-- Run after 20261118_ontology_review_status.sql on an existing table.
-- Fresh installs already use audit_status. Repeated execution preserves all data.
SET @ontology_has_old_audit_column = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dops_ontology' AND COLUMN_NAME = 'review_status'
);
SET @ontology_audit_rename_ddl = IF(@ontology_has_old_audit_column = 1,
  'ALTER TABLE `dops_ontology`
     CHANGE COLUMN `review_status` `audit_status` VARCHAR(16) NOT NULL DEFAULT ''pending''
     COMMENT ''pending未审核/approved通过/rejected驳回''',
  'SELECT 1'
);
PREPARE ontology_audit_rename FROM @ontology_audit_rename_ddl;
EXECUTE ontology_audit_rename;
DEALLOCATE PREPARE ontology_audit_rename;
