SELECT
  i.item_number,
  i.item_descrip1,
  i.item_descrip2,

  cc.classcode_code     AS class_code,
  cc.classcode_descrip  AS class_code_description,

  isite.itemsite_warehous_id AS warehouse_id,
  COALESCE(isite.itemsite_qtyonhand, 0) AS qty_on_hand,

  CASE
    WHEN NULLIF(BTRIM(isite.itemsite_planning_type), '') IS NULL THEN 'NO'
    ELSE 'YES'
  END AS mrp_enabled,

  i.item_created::date          AS item_created_date,
  tx.first_trans_date::date     AS first_transaction_date,
  tx.last_trans_date::date      AS last_transaction_date

FROM public.item i
JOIN public.itemsite isite
  ON isite.itemsite_item_id = i.item_id

LEFT JOIN public.classcode cc
  ON cc.classcode_id = i.item_classcode_id

LEFT JOIN (
  SELECT
    ih.invhist_itemsite_id,
    MIN(ih.invhist_transdate) AS first_trans_date,
    MAX(ih.invhist_transdate) AS last_trans_date
  FROM public.invhist ih
  GROUP BY ih.invhist_itemsite_id
) tx
  ON tx.invhist_itemsite_id = isite.itemsite_id

WHERE isite.itemsite_warehous_id = 51
ORDER BY i.item_number;
