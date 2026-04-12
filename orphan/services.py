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
    expiry_after: str = "",
    expiry_before: str = "",
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
        sql += " AND lower(q.source_status) = :flag_like"
        params["flag_like"] = flag_q.lower()

    if auth_numbers:
        # Build a parameter list (:a0, :a1, ...)
        placeholders = []
        for i, val in enumerate(auth_numbers):
            key = f"a{i}"
            placeholders.append(f":{key}")
            params[key] = val
        sql += f" AND CAST(q.authorisation_number AS NVARCHAR(100)) IN ({', '.join(placeholders)})"

    if expiry_after:
        sql += " AND q.orphan_me_expiry_date >= :expiry_after"
        params["expiry_after"] = expiry_after

    if expiry_before:
        sql += " AND q.orphan_me_expiry_date <= :expiry_before"
        params["expiry_before"] = expiry_before

    # Ordering (optional, makes list stable)
    sql += " ORDER BY smpc_id desc "

    with get_engine().connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


QUERY_SMPC_LIST_BASE = """
SELECT [id]
      ,[S1_Name_of_Medicinal_product]       AS product_name
      ,[S2_Composition]                     AS composition
      ,[S3_pharmaceutical_form]             AS dose_form
      ,[S_6_1_excipients]                   AS excipients
      ,[S_6_3_shelf_life]                   AS shelf_life
      ,[S_7_marketing_authorisation_holder] AS auth_holder
      ,[s_8_authorisation_number]           AS auth_number
      ,[S_9_authorisation_date]             AS auth_date
      ,[S_10_revision_date]                 AS revision_date
      ,[S_4_1_therapeutic_indications]      AS therapeutic_indications
FROM [Staging].[SMPC]
WHERE id > 160
"""

QUERY_SMPC_DETAIL = """
SELECT
    s.*,
    sub.preferred_name AS ai_ema_substance,
    sub.sms_id AS ai_ema_sms_id,
    sas.rationale_substance_match AS ai_rationale,
    sas.confidence_substance_match AS ai_confidence
FROM [Staging].[SMPC] s
LEFT OUTER JOIN Staging.SMPC_Active_Substance sas ON sas.SMPC_id = s.id AND sas.Substance_role = 'Active'
LEFT OUTER JOIN Staging.Substance sub ON sub.substance_sk = sas.Substance_sk
WHERE s.id = :smpc_id
"""

QUERY_SMPC_EMA_SUBSTANCES = """
SELECT
    s.[S2_Composition] AS smpc_composition,
    s.[S_6_1_excipients] AS smpc_excipients,
    sas.[Substance_role],
    sub.[preferred_name] AS ema_preferred_name,
    subN.[name_text] AS mah_specified_name,
    sas.[rationale_synonym_match],
    sub.sms_id AS preferred_name_sms_id,
    subN.sms_id AS synonym_sms_id
FROM Staging.SMPC s
INNER JOIN [Staging].[SMPC_Active_Substance] sas ON sas.smpc_id = s.id
INNER JOIN Staging.Substance sub ON sub.substance_sk = sas.Substance_sk
LEFT OUTER JOIN [Staging].[Substance_Name] subN ON subN.[substance_name_sk] = sas.[Synonym_id]
WHERE s.id = :smpc_id
"""


def load_smpc_list_df(
    product_q: str = "",
    composition_q: str = "",
    auth_holder_q: str = "",
    therapeutic_indications_q: str = "",
    auth_date_after: str = "",
    auth_date_before: str = "",
    revision_date_after: str = "",
    revision_date_before: str = "",
    top_n: int = 2000,
) -> pd.DataFrame:
    sql = f"SELECT TOP ({int(top_n)}) * FROM ( {QUERY_SMPC_LIST_BASE} ) AS q WHERE 1=1"
    params = {}

    if product_q:
        sql += " AND q.product_name LIKE :product_like"
        params["product_like"] = f"%{product_q}%"

    if composition_q:
        sql += " AND q.composition LIKE :composition_like"
        params["composition_like"] = f"%{composition_q}%"

    if auth_holder_q:
        sql += " AND q.auth_holder LIKE :auth_holder_like"
        params["auth_holder_like"] = f"%{auth_holder_q}%"

    if therapeutic_indications_q:
        sql += " AND q.therapeutic_indications LIKE :therapeutic_like"
        params["therapeutic_like"] = f"%{therapeutic_indications_q}%"

    if auth_date_after:
        sql += " AND q.auth_date >= :auth_after"
        params["auth_after"] = auth_date_after

    if auth_date_before:
        sql += " AND q.auth_date <= :auth_before"
        params["auth_before"] = auth_date_before

    if revision_date_after:
        sql += " AND q.revision_date >= :rev_after"
        params["rev_after"] = revision_date_after

    if revision_date_before:
        sql += " AND q.revision_date <= :rev_before"
        params["rev_before"] = revision_date_before

    sql += " ORDER BY q.id DESC"

    with get_engine().connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def load_smpc_detail(smpc_id: int) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql_query(text(QUERY_SMPC_DETAIL), conn, params={"smpc_id": smpc_id})


def load_smpc_ema_substances(smpc_id: int) -> pd.DataFrame:
    """Load detailed EMA substance matching data for an SMPC."""
    with get_engine().connect() as conn:
        return pd.read_sql_query(text(QUERY_SMPC_EMA_SUBSTANCES), conn, params={"smpc_id": smpc_id})


QUERY_SMPC_SIMILAR_PRODUCTS = """
SELECT
    s2.id,
    s2.[s_8_authorisation_number] AS auth_number,
    LEFT(s2.[S1_Name_of_Medicinal_product], 160) AS product_name_short,
    CONCAT(s2.[s_8_authorisation_number], ' - ', LEFT(s2.[S1_Name_of_Medicinal_product], 160)) AS similar_product_label
FROM Staging.SMPC s
INNER JOIN [Staging].[SMPC_Active_Substance] sas ON sas.smpc_id = s.id AND sas.[Substance_role] = 'Active'
INNER JOIN [Staging].[SMPC_Active_Substance] sas2 ON sas.[Substance_sk] = sas2.[Substance_sk] AND sas.smpc_id <> sas2.smpc_id
INNER JOIN Staging.SMPC s2 ON s2.id = sas2.smpc_id
WHERE s.id > 160 AND s2.id > 160 AND s.id = :smpc_id
"""


def load_smpc_similar_products(smpc_id: int) -> pd.DataFrame:
    """Load similar products based on shared active substances."""
    with get_engine().connect() as conn:
        return pd.read_sql_query(text(QUERY_SMPC_SIMILAR_PRODUCTS), conn, params={"smpc_id": smpc_id})


QUERY_IDMP_MA = """
SELECT
    ma.MA_sk,
    ma.Authorisation_Number,
    ma.First_Authorisation_Date,
    ma.Authorisation_Status_denorm          AS Authorisation_Status,
    ma.Authorisation_Status_Date,
    ma.Procedure_Type_denorm                AS Procedure_Type,
    ma.Procedure_Start_date,
    ma.Procedure_End_date,
    ma.Validity_Start_Date,
    ma.Validity_End_Date,
    ma.Current_flag
FROM rim.MA_Marketing_Authorisation ma
WHERE ma.Current_flag = 1
ORDER BY ma.Authorisation_Number
"""

QUERY_IDMP_MP = """
SELECT
    mp.Med_Prod_sk,
    mp.MPID,
    mp.Internal_MPID,
    mp.Jurisdiction_denorm                  AS Jurisdiction,
    mp.Combined_dose_form_denorm            AS Combined_Dose_Form,
    mp.Orphan_designation,
    mp.Paediatric_use_indication_flag,
    mp.Additional_monitoring_flag,
    mpn.Full_Name,
    mpn.Name_type_denorm                    AS Name_Type,
    mpn.Is_Preferred,
    mpn.Invented_Name_Part,
    mpn.Scientific_Name_Part,
    mpn.Strength_Part,
    mpn.Pharmaceutical_Dose_Form_Part,
    mpn.Country_Code,
    mpn.Language_Code,
    ma.Authorisation_Number,
    ma.MA_sk
FROM rim.Medicinal_Products mp
INNER JOIN rim.MA_MP_Association assoc
    ON assoc.Med_Prod_sk = mp.Med_Prod_sk
   AND assoc.Current_flag = 1
INNER JOIN rim.MA_Marketing_Authorisation ma
    ON ma.MA_sk = assoc.MA_sk
   AND ma.Current_flag = 1
LEFT JOIN rim.Medicinal_Product_Names mpn
    ON mpn.Med_Prod_sk = mp.Med_Prod_sk
WHERE mp.Current_flag = 1
ORDER BY mp.Med_Prod_sk, mpn.Is_Preferred DESC, mpn.Full_Name
"""

QUERY_IDMP_AP = """
SELECT
    ap.AdmProd_sk,
    mp.Med_Prod_sk,
    mp.MPID,
    mp.Internal_MPID,
    ma.Authorisation_Number,
    ap.Dose_form_denorm                     AS Dose_Form,
    ap.Unit_of_presentation_denorm          AS Unit_of_Presentation,
    ap.Release_characteristics_denorm       AS Release_Characteristics,
    STRING_AGG(roa.Route_denorm, '; ')
        WITHIN GROUP (ORDER BY roa.Route_denorm) AS Routes,
    ap.Current_flag,
    ap.Validity_Start_Date
FROM rim.Administrable_Product ap
INNER JOIN rim.Medicinal_Products mp
    ON mp.Med_Prod_sk = ap.Med_Prod_sk
   AND mp.Current_flag = 1
INNER JOIN rim.MA_MP_Association assoc
    ON assoc.Med_Prod_sk = mp.Med_Prod_sk
   AND assoc.Current_flag = 1
INNER JOIN rim.MA_Marketing_Authorisation ma
    ON ma.MA_sk = assoc.MA_sk
   AND ma.Current_flag = 1
LEFT JOIN rim.Route_of_Administration roa
    ON roa.AdmProd_sk = ap.AdmProd_sk
WHERE ap.Current_flag = 1
GROUP BY
    ap.AdmProd_sk, mp.Med_Prod_sk, mp.MPID, mp.Internal_MPID,
    ma.Authorisation_Number,
    ap.Dose_form_denorm, ap.Unit_of_presentation_denorm,
    ap.Release_characteristics_denorm, ap.Current_flag, ap.Validity_Start_Date
ORDER BY ma.Authorisation_Number, ap.AdmProd_sk
"""


def load_idmp_product_master() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with get_engine().connect() as conn:
        ma = pd.read_sql_query(text(QUERY_IDMP_MA), conn)
        mp = pd.read_sql_query(text(QUERY_IDMP_MP), conn)
        ap = pd.read_sql_query(text(QUERY_IDMP_AP), conn)
    return ma, mp, ap


QUERY_IDMP_MA_FOR_ORPHAN = """
SELECT
    ma.MA_sk,
    ma.Authorisation_Number,
    ma.First_Authorisation_Date,
    ma.Authorisation_Status_denorm      AS Authorisation_Status,
    ma.Authorisation_Status_Date,
    ma.Procedure_Type_denorm            AS Procedure_Type,
    ma.Procedure_Start_date,
    ma.Procedure_End_date,
    ma.Validity_Start_Date,
    ma.Validity_End_Date
FROM rim.MA_Marketing_Authorisation ma
INNER JOIN rim.MHRA_OrphanDesignation od
    ON od.authorisation_number = ma.Authorisation_Number
WHERE ma.Current_flag = 1
  AND od.orphan_id = :orphan_id
"""

QUERY_IDMP_MP_FOR_ORPHAN = """
SELECT
    mp.Med_Prod_sk,
    mp.MPID,
    mp.Internal_MPID,
    mp.Jurisdiction_denorm              AS Jurisdiction,
    mp.Combined_dose_form_denorm        AS Combined_Dose_Form,
    mp.Orphan_designation,
    mp.Paediatric_use_indication_flag,
    mp.Additional_monitoring_flag,
    mpn.Full_Name,
    mpn.Name_type_denorm                AS Name_Type,
    mpn.Is_Preferred,
    mpn.Invented_Name_Part,
    mpn.Scientific_Name_Part,
    mpn.Strength_Part,
    mpn.Pharmaceutical_Dose_Form_Part,
    mpn.Country_Code,
    mpn.Language_Code,
    ma.Authorisation_Number
FROM rim.Medicinal_Products mp
INNER JOIN rim.MA_MP_Association assoc
    ON assoc.Med_Prod_sk = mp.Med_Prod_sk AND assoc.Current_flag = 1
INNER JOIN rim.MA_Marketing_Authorisation ma
    ON ma.MA_sk = assoc.MA_sk AND ma.Current_flag = 1
INNER JOIN rim.MHRA_OrphanDesignation od
    ON od.authorisation_number = ma.Authorisation_Number
LEFT JOIN rim.Medicinal_Product_Names mpn
    ON mpn.Med_Prod_sk = mp.Med_Prod_sk
WHERE mp.Current_flag = 1
  AND od.orphan_id = :orphan_id
ORDER BY mp.Med_Prod_sk, mpn.Is_Preferred DESC
"""

QUERY_IDMP_AP_FOR_ORPHAN = """
SELECT
    ap.AdmProd_sk,
    mp.Med_Prod_sk,
    mp.MPID,
    ma.Authorisation_Number,
    ap.Dose_form_denorm                 AS Dose_Form,
    ap.Unit_of_presentation_denorm      AS Unit_of_Presentation,
    ap.Release_characteristics_denorm   AS Release_Characteristics,
    STRING_AGG(roa.Route_denorm, '; ')
        WITHIN GROUP (ORDER BY roa.Route_denorm) AS Routes,
    ap.Validity_Start_Date
FROM rim.Administrable_Product ap
INNER JOIN rim.Medicinal_Products mp
    ON mp.Med_Prod_sk = ap.Med_Prod_sk AND mp.Current_flag = 1
INNER JOIN rim.MA_MP_Association assoc
    ON assoc.Med_Prod_sk = mp.Med_Prod_sk AND assoc.Current_flag = 1
INNER JOIN rim.MA_Marketing_Authorisation ma
    ON ma.MA_sk = assoc.MA_sk AND ma.Current_flag = 1
INNER JOIN rim.MHRA_OrphanDesignation od
    ON od.authorisation_number = ma.Authorisation_Number
LEFT JOIN rim.Route_of_Administration roa
    ON roa.AdmProd_sk = ap.AdmProd_sk
WHERE ap.Current_flag = 1
  AND od.orphan_id = :orphan_id
GROUP BY ap.AdmProd_sk, mp.Med_Prod_sk, mp.MPID,
         ma.Authorisation_Number, ap.Dose_form_denorm,
         ap.Unit_of_presentation_denorm,
         ap.Release_characteristics_denorm, ap.Validity_Start_Date
ORDER BY ap.AdmProd_sk
"""


def load_idmp_for_orphan(orphan_id: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    params = {"orphan_id": orphan_id}
    with get_engine().connect() as conn:
        ma = pd.read_sql_query(text(QUERY_IDMP_MA_FOR_ORPHAN), conn, params=params)
        mp = pd.read_sql_query(text(QUERY_IDMP_MP_FOR_ORPHAN), conn, params=params)
        ap = pd.read_sql_query(text(QUERY_IDMP_AP_FOR_ORPHAN), conn, params=params)
    return ma, mp, ap


def load_page2_details(orphan_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    with get_engine().connect() as conn:
        a = pd.read_sql_query(text(QUERY_PAGE2_A), conn, params={"orphan_id": orphan_id})
        b = pd.read_sql_query(text(QUERY_PAGE2_B), conn, params={"orphan_id": orphan_id})
        smpc_url = None
        if not b.empty and "SMPC_URL" in b.columns:
            smpc_url = b["SMPC_URL"].iloc[0]  # could still be None

        logger.info("SMPC URL: %s", smpc_url)  # safe even if None
    return a, b