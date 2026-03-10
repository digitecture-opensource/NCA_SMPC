import pandas as pd
from sqlalchemy import text
from .dbconnect import get_engine
import logging
logger = logging.getLogger("orphan.views")

QUERY_PAGE1_BASE = """
SELECT   [orphan_id]
      ,  cast(smpc_id as varchar(100)) as smpc_id
      ,[source_status]
      ,[source_file]
      ,[product_name]
      ,[active_substance]
      ,[orphan_condition]
      ,[od_indication]
      ,[designation_number_raw]
      ,[authorisation_number]
      ,[designation_suffix]
      ,[orphan_me_expiry_date]
      ,[designation_removed_date]
     
  FROM [rim].[MHRA_OrphanDesignation]
  
"""

QUERY_PAGE2_A = """
SELECT
      s.[S1_Name_of_Medicinal_product] AS [product_name_smpc]
    , od.product_name AS [product_name_od]
    , s.[S2_Composition] AS [composition_smpc]
    , od.[active_substance] AS [active_substance_od]
      , od.[designation_suffix] AS "Designation_suffix"
 
    , sub.preferred_name AS [ai_ema_substance]
    , sub.sms_id AS [ai_ema_sms_id]
    , sas.rationale_substance_match AS [ai_rationale]
    , sas.confidence_substance_match AS [ai_confidence]
    , s.[S3_pharmaceutical_form] AS [dose_form_smpc]
    , s.[S_7_marketing_authorisation_holder] AS [ma_holder_smpc]
    , od.authorisation_number AS [pl_number_od]
    , s.[s_8_authorisation_number] AS [pl_number_smpc]
    , s.[S_9_authorisation_date] AS [auth_date_smpc]
    , s.[S_10_revision_date] AS [revision_date_smpc]

FROM  [rim].[MHRA_OrphanDesignation] od 
left outer JOIN [Staging].[SMPC] s on od.smpc_id = s.id
LEFT OUTER JOIN Staging.SMPC_Active_Substance sas on sas.SMPC_id = s.id and Substance_role = 'Active'
LEFT OUTER JOIN Staging.Substance sub on sub.substance_sk = sas.Substance_sk
WHERE od.orphan_id = :orphan_id;
"""

QUERY_PAGE2_B = """
SELECT
      od.authorisation_number AS [pl_number_od]
    , od.od_indication AS [od_indication]
     , od.[designation_number_raw] AS [designation_number_raw]
     , od.[orphan_condition] AS [orphan_condition]
    , s.[S_4_1_therapeutic_indications]  AS [indications]
    , s.[S_4_3_contraindications]        AS [contraindications]
    , s.[S_4_4_warnings_precautions]     AS [warnings_precautions]
    , s.[S_4_5_interactions]             AS [interactions]
    , s.[S_4_6_pregnancy_lactation]      AS [pregnancy_lactation]
    , s.[S_4_7_driving_machines]         AS [driving_machines]
    , s.[S_4_8_undesirable_effects]      AS [undesirable_effects]
    , s.[S_4_9_overdose]                 AS [overdose]
    , s.[S_6_3_shelf_life]               AS [shelf_life]
    , s.[S_6_4_storage]                  AS [storage]
    , s.[S_6_5_container_description]    AS [container_description]
    , s.[S_6_6_handling_disposal]        AS [handling_disposal]
    
    , smd.[Metadata_Storage_Path] AS SMPC_URL
FROM [rim].[MHRA_OrphanDesignation] od
left outer JOIN [Staging].[SMPC] s on od.smpc_id = s.id
left outer join [Staging].[SMPC_Meta_data] smd on smd.smpc_id = s.id
WHERE od.orphan_id = :orphan_id;
"""


def load_page1_df(
    product_q: str = "",
    substance_q: str = "",
    flag_q: str = "",
    auth_numbers: list[str] | None = None,
    top_n: int = 2000,
) -> pd.DataFrame:
    """
    Server-side filtering in SQL (LIKE %...%) + optional auth list filter.
    Limits rows with TOP to keep the page snappy.
    """
    sql = f"SELECT TOP ({int(top_n)}) * FROM ( {QUERY_PAGE1_BASE} ) as q WHERE 1=1 "
    params = {}

    if product_q:
        sql += " AND q.product_name LIKE :product_like"
        params["product_like"] = f"%{product_q}%"

    if substance_q:
        sql += " AND q.active_substance LIKE :substance_like"
        params["substance_like"] = f"%{substance_q}%"
    if flag_q:
        sql += " AND lower(q.source_status) =  :flag_like"
        params["flag_like"] = f"{flag_q}".lower()

    if auth_numbers:
        # Build a parameter list (:a0, :a1, ...)
        placeholders = []
        for i, val in enumerate(auth_numbers):
            key = f"a{i}"
            placeholders.append(f":{key}")
            params[key] = val
        sql += f" AND CAST(q.authorisation_number AS NVARCHAR(100)) IN ({', '.join(placeholders)})"

    # Ordering (optional, makes list stable)
    sql += " ORDER BY smpc_id desc "

    with get_engine().connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def load_page2_details(orphan_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    with get_engine().connect() as conn:
        a = pd.read_sql_query(text(QUERY_PAGE2_A), conn, params={"orphan_id": orphan_id})
        b = pd.read_sql_query(text(QUERY_PAGE2_B), conn, params={"orphan_id": orphan_id})
        smpc_url = None
        if not b.empty and "SMPC_URL" in b.columns:
            smpc_url = b["SMPC_URL"].iloc[0]  # could still be None

        logger.info("SMPC URL: %s", smpc_url)  # safe even if None
    return a, b