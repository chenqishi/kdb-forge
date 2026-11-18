-- Upgrade an existing ontology table. Fresh installs use 20261117_ontology.sql first.
-- Existing rows are pending review, never implicitly approved. Safe to rerun.
SET @ontology_has_review = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dops_ontology' AND COLUMN_NAME = 'review_status'
);
SET @ontology_review_ddl = IF(@ontology_has_review = 0,
  'ALTER TABLE `dops_ontology`
     ADD COLUMN `review_status` VARCHAR(16) NOT NULL DEFAULT ''pending'' COMMENT ''pending待审/approved通过/rejected驳回'' AFTER `status`,
     MODIFY COLUMN `status` VARCHAR(16) NOT NULL DEFAULT ''active'' COMMENT ''active启用/inactive停用，与审核状态独立'',
     DROP INDEX `idx_scope_status`,
     ADD INDEX `idx_scope_status` (`client`,`product`,`status`,`review_status`,`del_flag`)',
  'SELECT 1'
);
PREPARE ontology_review_upgrade FROM @ontology_review_ddl;
EXECUTE ontology_review_upgrade;
DEALLOCATE PREPARE ontology_review_upgrade;
-- Preserve the non-effective behavior of legacy drafts. The version records this change.
UPDATE `dops_ontology` SET `status` = 'inactive', `revision` = `revision` + 1
WHERE `status` = 'draft';
