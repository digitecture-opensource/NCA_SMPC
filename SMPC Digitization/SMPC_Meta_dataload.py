import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

ERROR_FILE = "errors_smpc_meta_data.jsonl"


# ----------------------------
# DB Connection (as provided)
# ----------------------------
DB_SERVER = os.getenv("DB_SERVER")
if not os.getenv("DB_SERVER"):
    load_dotenv(r"C:\Users\anilp\OneDrive - digitecture.co.uk\Code\CV Managament_Github JS Code\CV_Management\.env")

driver   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
server   = os.getenv("DB_SERVER")
database = os.getenv("DB_DATABASE")
uid      = os.getenv("DB_USERNAME")
pwd      = os.getenv("DB_PASSWORD")

params = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={uid};"
    f"PWD={pwd};"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)

conn_str = f"mssql+pyodbc:///?odbc_connect={quote_plus(params)}"


# ----------------------------
# Helpers
# ----------------------------
def parse_created_utc(created_str: Optional[str]) -> Optional[datetime]:
    """
    Parses ISO strings like '2025-09-12T05:55:54Z' into a naive datetime (UTC).
    If parsing fails, returns None.
    """
    if not created_str:
        return None
    try:
        if created_str.endswith("Z"):
            created_str = created_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(created_str)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def to_json_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def join_highlight_content(item: Dict[str, Any]) -> (Optional[str], Optional[str]):
    """
    Source:
      "@search.highlights": { "content": [ "...", "..." ] }
    """
    highlights = item.get("@search.highlights") or {}
    content_list = highlights.get("content")
    if not isinstance(content_list, list):
        return None, None

    joined = "\n\n----\n\n".join(str(x) for x in content_list if x is not None).strip()
    return (joined or None), to_json_str(content_list)


def write_error_json(error_obj: Dict[str, Any]) -> None:
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(error_obj, ensure_ascii=False) + "\n")


# ----------------------------
# SQL
# ----------------------------
GET_SMPC_ID_SQL = text("""
    SELECT MAX(id) AS smpc_id
    FROM [Staging].[SMPC]
    WHERE [Source_file_name] = :source_file_name
""")

# PK is SMPC_Id, so "duplicate" means a second record for same SMPC (we upsert).
UPSERT_SQL = text("""
    IF EXISTS (SELECT 1 FROM [Staging].[SMPC_Meta_data] WHERE [SMPC_Id] = :SMPC_Id)
    BEGIN
        UPDATE [Staging].[SMPC_Meta_data]
        SET
            [Agency_id]               = :Agency_id,
            [Search_Score]            = :Search_Score,
            [Rev_Label]               = :Rev_Label,
            [Highlights_Content_Text] = :Highlights_Content_Text,
            [Highlights_Content_JSON] = :Highlights_Content_JSON,
            [Metadata_Storage_Path]   = :Metadata_Storage_Path,
            [Metadata_Storage_Name]   = :Metadata_Storage_Name,
            [Metadata_Storage_Size]   = :Metadata_Storage_Size,
            [Product_Name]            = :Product_Name,
            [Created_UTC]             = :Created_UTC,
            [Release_State]           = :Release_State,
            [Keywords]                = :Keywords,
            [Title]                   = :Title,
            [Territory]               = :Territory,
            [File_Name]               = :File_Name,
            [Doc_Type]                = :Doc_Type,
            [PL_Number_JSON]          = :PL_Number_JSON,
            [Suggestions_JSON]        = :Suggestions_JSON,
            [Substance_Name_JSON]     = :Substance_Name_JSON,
            [Facets_JSON]             = :Facets_JSON,
            [Raw_Item_JSON]           = :Raw_Item_JSON,
            [Loaded_UTC]              = SYSUTCDATETIME()
        WHERE [SMPC_Id] = :SMPC_Id;
    END
    ELSE
    BEGIN
        INSERT INTO [Staging].[SMPC_Meta_data]
        (
            [SMPC_Id],
            [Agency_id],
            [Search_Score],
            [Rev_Label],
            [Highlights_Content_Text],
            [Highlights_Content_JSON],
            [Metadata_Storage_Path],
            [Metadata_Storage_Name],
            [Metadata_Storage_Size],
            [Product_Name],
            [Created_UTC],
            [Release_State],
            [Keywords],
            [Title],
            [Territory],
            [File_Name],
            [Doc_Type],
            [PL_Number_JSON],
            [Suggestions_JSON],
            [Substance_Name_JSON],
            [Facets_JSON],
            [Raw_Item_JSON]
        )
        VALUES
        (
            :SMPC_Id,
            :Agency_id,
            :Search_Score,
            :Rev_Label,
            :Highlights_Content_Text,
            :Highlights_Content_JSON,
            :Metadata_Storage_Path,
            :Metadata_Storage_Name,
            :Metadata_Storage_Size,
            :Product_Name,
            :Created_UTC,
            :Release_State,
            :Keywords,
            :Title,
            :Territory,
            :File_Name,
            :Doc_Type,
            :PL_Number_JSON,
            :Suggestions_JSON,
            :Substance_Name_JSON,
            :Facets_JSON,
            :Raw_Item_JSON
        );
    END
""")


# ----------------------------
# Mapping
# ----------------------------
def get_smpc_id(conn, source_file_name: str) -> Optional[int]:
    res = conn.execute(GET_SMPC_ID_SQL, {"source_file_name": source_file_name}).mappings().first()
    if not res:
        return None
    return res.get("smpc_id")


def map_item_to_row(smpc_id: int, item: Dict[str, Any], agency_id: int = 6) -> Dict[str, Any]:
    highlights_text, highlights_json = join_highlight_content(item)

    return {
        "SMPC_Id": smpc_id,
        "Agency_id": agency_id,

        "Search_Score": item.get("@search.score"),
        "Rev_Label": item.get("rev_label"),

        "Highlights_Content_Text": highlights_text,
        "Highlights_Content_JSON": highlights_json,

        "Metadata_Storage_Path": item.get("metadata_storage_path"),
        "Metadata_Storage_Name": item.get("metadata_storage_name"),
        "Metadata_Storage_Size": item.get("metadata_storage_size"),

        "Product_Name": item.get("product_name"),
        "Created_UTC": parse_created_utc(item.get("created")),
        "Release_State": item.get("release_state"),
        "Keywords": item.get("keywords"),
        "Title": item.get("title"),
        "Territory": item.get("territory"),
        "File_Name": item.get("file_name"),
        "Doc_Type": item.get("doc_type"),

        "PL_Number_JSON": to_json_str(item.get("pl_number")),
        "Suggestions_JSON": to_json_str(item.get("suggestions")),
        "Substance_Name_JSON": to_json_str(item.get("substance_name")),
        "Facets_JSON": to_json_str(item.get("facets")),

        "Raw_Item_JSON": to_json_str(item),
    }


# ----------------------------
# Main load function
# ----------------------------
def load_json_to_db(engine: Engine, json_path: str, agency_id: int = 6) -> None:
    # reset per run (comment out if you want append-only error logs)
    if os.path.exists(ERROR_FILE):
        os.remove(ERROR_FILE)

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    items: List[Dict[str, Any]] = payload.get("value") or []
    if not isinstance(items, list):
        raise ValueError("JSON payload does not contain a list under 'value'.")

    upserted = 0
    skipped = 0

    with engine.begin() as conn:
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                skipped += 1
                write_error_json({
                    "error": "Row is not an object/dict",
                    "index": idx,
                    "row": item,
                })
                continue

            source_file_name = item.get("title")
            if not source_file_name:
                skipped += 1
                write_error_json({
                    "error": "Missing file_name in item",
                    "index": idx,
                    "row": item,
                })
                continue

            smpc_id = get_smpc_id(conn, source_file_name)
            if not smpc_id:
                skipped += 1
                write_error_json({
                    "error": "No matching SMPC.id found for file_name (MAX(id) returned NULL)",
                    "index": idx,
                    "file_name": source_file_name,
                    "row": item,
                })
                continue

            row = map_item_to_row(smpc_id, item, agency_id=agency_id)
            conn.execute(UPSERT_SQL, row)
            upserted += 1

    logging.info("Finished. Upserted=%s | Skipped=%s", upserted, skipped)
    if skipped:
        logging.info("Errors written to: %s", os.path.abspath(ERROR_FILE))


def main():
    engine = create_engine(conn_str, fast_executemany=True)

    import argparse
    parser = argparse.ArgumentParser(description="Load MHRA Search JSON into Staging.SMPC_Meta_data.")
    parser.add_argument("--json", required=True, help="Path to JSON file (must contain top-level 'value' array).")
    parser.add_argument("--agency-id", type=int, default=6, help="Agency_id to store (default 6 = MHRA).")
    args = parser.parse_args()

    load_json_to_db(engine, args.json, agency_id=args.agency_id)


if __name__ == "__main__":
    main()