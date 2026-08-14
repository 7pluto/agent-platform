USE `ry-vue`;
DELIMITER //

DROP PROCEDURE IF EXISTS repair_display_column//
CREATE PROCEDURE repair_display_column(IN table_value VARCHAR(64), IN column_value VARCHAR(64))
BEGIN
    SET @column_ref = CONCAT('`', REPLACE(column_value, '`', '``'), '`');
    SET @candidate = CONCAT(
        'CONVERT(CAST(CONVERT(', @column_ref,
        ' USING latin1) AS BINARY) USING utf8mb4)'
    );
    SET @repair_statement = CONCAT(
        'UPDATE `ry-vue`.`', REPLACE(table_value, '`', '``'), '` ',
        'SET ', @column_ref, ' = ', @candidate, ' ',
        'WHERE ', @column_ref, ' IS NOT NULL ',
        'AND CONVERT(', @column_ref, ' USING latin1) NOT LIKE ''%?%'' ',
        'AND ', @candidate, ' IS NOT NULL ',
        'AND BINARY ', @column_ref, ' <> BINARY ', @candidate
    );
    PREPARE repair_query FROM @repair_statement;
    EXECUTE repair_query;
    DEALLOCATE PREPARE repair_query;
END//

DELIMITER ;
START TRANSACTION;
CALL repair_display_column('sys_dept', 'dept_name');
CALL repair_display_column('sys_dept', 'leader');
CALL repair_display_column('sys_user', 'nick_name');
CALL repair_display_column('sys_user', 'remark');
CALL repair_display_column('sys_post', 'post_name');
CALL repair_display_column('sys_post', 'remark');
CALL repair_display_column('sys_role', 'role_name');
CALL repair_display_column('sys_role', 'remark');
CALL repair_display_column('sys_menu', 'remark');
CALL repair_display_column('sys_dict_type', 'dict_name');
CALL repair_display_column('sys_dict_type', 'remark');
CALL repair_display_column('sys_dict_data', 'dict_label');
CALL repair_display_column('sys_dict_data', 'remark');
CALL repair_display_column('sys_config', 'config_name');
CALL repair_display_column('sys_config', 'config_value');
CALL repair_display_column('sys_config', 'remark');
CALL repair_display_column('sys_notice', 'notice_title');
CALL repair_display_column('sys_notice', 'notice_content');
CALL repair_display_column('sys_job', 'job_name');
CALL repair_display_column('sys_job', 'remark');
COMMIT;
DROP PROCEDURE repair_display_column;
