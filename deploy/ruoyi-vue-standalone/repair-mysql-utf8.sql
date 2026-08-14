DELIMITER //

DROP PROCEDURE IF EXISTS repair_mojibake//
CREATE PROCEDURE repair_mojibake()
BEGIN
    DECLARE finished INTEGER DEFAULT 0;
    DECLARE table_name_value VARCHAR(64);
    DECLARE column_name_value VARCHAR(64);
    DECLARE changed_total BIGINT DEFAULT 0;
    DECLARE text_columns CURSOR FOR
        SELECT TABLE_NAME, COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'ry-vue'
          AND DATA_TYPE IN ('char', 'varchar', 'tinytext', 'text', 'mediumtext', 'longtext');
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET finished = 1;

    OPEN text_columns;
    repair_loop: LOOP
        FETCH text_columns INTO table_name_value, column_name_value;
        IF finished = 1 THEN
            LEAVE repair_loop;
        END IF;

        SET @qualified_column = CONCAT('`', REPLACE(column_name_value, '`', '``'), '`');
        SET @candidate = CONCAT(
            'CONVERT(CAST(CONVERT(', @qualified_column,
            ' USING latin1) AS BINARY) USING utf8mb4)'
        );
        SET @repair_statement = CONCAT(
            'UPDATE `ry-vue`.`', REPLACE(table_name_value, '`', '``'), '` ',
            'SET ', @qualified_column, ' = ', @candidate, ' ',
            'WHERE ', @qualified_column, ' IS NOT NULL ',
            'AND CONVERT(', @qualified_column, ' USING latin1) NOT LIKE ''%?%'' ',
            'AND ', @candidate, ' IS NOT NULL ',
            'AND BINARY ', @qualified_column, ' <> BINARY ', @candidate
        );
        PREPARE repair_query FROM @repair_statement;
        EXECUTE repair_query;
        SET changed_total = changed_total + ROW_COUNT();
        DEALLOCATE PREPARE repair_query;
    END LOOP;
    CLOSE text_columns;

    SELECT changed_total AS repaired_values;
END//

DELIMITER ;
START TRANSACTION;
CALL repair_mojibake();
COMMIT;
DROP PROCEDURE repair_mojibake;