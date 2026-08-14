START TRANSACTION;

UPDATE `ry-vue`.`sys_menu`
SET `menu_name` = CONVERT(
    CAST(CONVERT(`menu_name` USING latin1) AS BINARY)
    USING utf8mb4
)
WHERE `menu_name` IS NOT NULL
  AND CONVERT(`menu_name` USING latin1) NOT LIKE '%?%'
  AND CONVERT(
      CAST(CONVERT(`menu_name` USING latin1) AS BINARY)
      USING utf8mb4
  ) IS NOT NULL
  AND BINARY `menu_name` <> BINARY CONVERT(
      CAST(CONVERT(`menu_name` USING latin1) AS BINARY)
      USING utf8mb4
  );

SELECT ROW_COUNT() AS repaired_menu_names;
COMMIT;
