# Org_Step_30_load_MHRA_orphan_register.py
# Step 30: Load MHRA Orphan Register CSVs (current + expired) into IDMP (SQL Server)
# Assumes:
#   - Table RIM.MHRA_OrphanDesignation already exists
#   - Stored proc RIM.usp_upsert_mhra_orphan_designation already exists
#
# It:
#   - Splits comma-separated "Designation number" into 1 row per token
#   - Extracts authorisation number as the FIRST licence in the token (e.g. "PLGB 52115/0001")
#   - Extracts OD suffix (OD1/OD2/...)
#
# Usage (from run_pipeline.py):
#   from Org_Step_30_load_MHRA_orphan_register import run_step_30_load_mhra_orphan_register
#   run_step_30_load_mhra_orphan_register(current_csv_path=..., expired_csv_path=...)

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
from sqlalchemy import text

UPSERT_SQL = text("""
EXEC rim.usp_upsert_mhra_orphan_designation
     @source_status            = :source_status,
     @source_file              = :source_file,
     @source_rownum            = :source_rownum,
     @product_name             = :product_name,
     @active_substance         = :active_substance,
     @orphan_condition         = :orphan_condition,
     @od_indication            = :od_indication,
     @designation_number_raw   = :designation_number_raw,
     @authorisation_number     = :authorisation_number,
     @designation_suffix       = :designation_suffix,
     @orphan_me_expiry_date    = :orphan_me_expiry_date,
     @designation_removed_date = :designation_removed_date;
""")
Update_SMPC_SQL = text(""" 
    update rim.MHRA_OrphanDesignation set smpc_id = s.id
  from Staging.SMPC s where s.s_8_authorisation_number = authorisation_number
  and authorisation_number is null """)


# Prefix is "PL", "PLGB", etc. (user said could be any 4 chars, we allow 2..6)
AUTH_RE = re.compile(r"(?P<prefix>[A-Z0-9]{2,6})\s*(?P<num>\d{1,6}/\d{3,4})")
OD_RE = re.compile(r"/\s*(OD\d+)\b", re.IGNORECASE)

def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\u00A0", " ").strip()
    s = s.replace("–", "-")  # en-dash to hyphen
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ,;")

def split_designations(cell: str) -> List[str]:
    s = _clean(cell)
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p and str(p).strip()]
    return [_clean(p) for p in parts if _clean(p)]

def extract_authorisation_number(designation_token: str) -> Optional[str]:
    """
    Extract FIRST authorisation number from token.
    Examples:
      "PLGB 52115/0001 - 0002/OD2" => "PLGB 52115/0001"
      "PL 16189/0148-0149/OD1"     => "PL 16189/0148"
    """
    s = _clean(designation_token)
    m = AUTH_RE.search(s)
    if not m:
        return None
    return f"{m.group('prefix').upper()} {m.group('num')}"

def extract_designation_suffix(designation_token: str) -> Optional[str]:
    s = _clean(designation_token)
    m = OD_RE.search(s)
    return m.group(1).upper() if m else None

def parse_date_ddmmyyyy(v) -> Optional[str]:
    s = _clean(v)
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None

def read_mhra_orphan_csv(csv_path: Path) -> pd.DataFrame:
    """
    MHRA orphan CSV format:
      - Row 0: guidance text
      - Row 1: header row
      - Row 2+: data
    """
    raw = pd.read_csv(csv_path, encoding="cp1252", header=None)
    headers = [str(h).strip() for h in raw.iloc[1].tolist()]
    df = raw.iloc[2:].copy()
    df.columns = headers
    return df.reset_index(drop=True)

def _find_col_like(df: pd.DataFrame, startswith: str) -> str:
    sw = startswith.strip().lower()
    for c in df.columns:
        if str(c).strip().lower().startswith(sw):
            return c
    raise KeyError(f"Could not find a column like '{startswith}'. Columns: {list(df.columns)}")

def run_step_30_load_mhra_orphan_register(
    current_csv_path: str,
    expired_csv_path: str
) -> None:
    """
    Pipeline Step 30: Load MHRA orphan register CSVs into existing table via existing stored proc.
    """
    from dbconnect import get_engine_idmp
    engine = get_engine_idmp()

    def _load_one(csv_path: str, source_status: str) -> int:
        p = Path(csv_path)
        if not p.exists():
            raise FileNotFoundError(f"CSV not found: {p}")

        df = read_mhra_orphan_csv(p)

        c_product = _find_col_like(df, "Product name")
        c_active  = _find_col_like(df, "Active substance")
        c_cond    = _find_col_like(df, "Orphan Condition")
        c_ind     = _find_col_like(df, "OD Indication")
        c_desig   = _find_col_like(df, "Designation number")
        c_expiry  = _find_col_like(df, "Orphan Market Exclusivity Expiry date")

        # Only exists in expired file
        c_removed = None
        for c in df.columns:
            if "designation removed" in str(c).strip().lower():
                c_removed = c
                break

        payload: List[Dict[str, Any]] = []

        for i, r in df.iterrows():
            product_name = _clean(r.get(c_product)) or None
            active_substance = _clean(r.get(c_active)) or None
            orphan_condition = _clean(r.get(c_cond)) or None
            od_indication = _clean(r.get(c_ind)) or None

            expiry = parse_date_ddmmyyyy(r.get(c_expiry))
            removed = parse_date_ddmmyyyy(r.get(c_removed)) if c_removed else None

            for tok in split_designations(r.get(c_desig)):
                payload.append({
                    "source_status": source_status,
                    "source_file": str(p),
                    "source_rownum": int(i + 1),
                    "product_name": product_name,
                    "active_substance": active_substance,
                    "orphan_condition": orphan_condition,
                    "od_indication": od_indication,
                    "designation_number_raw": tok,
                    "authorisation_number": extract_authorisation_number(tok),
                    "designation_suffix": extract_designation_suffix(tok),
                    "orphan_me_expiry_date": expiry,
                    "designation_removed_date": removed,
                })

        if not payload:
            return 0

        with engine.begin() as conn:
            rows = conn.execute(text("""
            SELECT
              s.name AS schema_name,
              p.name AS proc_name
            FROM sys.procedures p
            JOIN sys.schemas s ON s.schema_id = p.schema_id
            WHERE s.name = 'RIM'
              AND p.name = 'usp_upsert_mhra_orphan_designation';
            """)).fetchall()
            print("PROC FOUND:", rows)
            print(conn.execute(text("SELECT SUSER_SNAME(), ORIGINAL_LOGIN(), SYSTEM_USER")).fetchone())
            conn.execute(UPSERT_SQL, payload)
            conn.execute(Update_SMPC_SQL)
            

        return len(payload)

    n_current = _load_one(current_csv_path, "current")
    n_expired = _load_one(expired_csv_path, "expired")

    print(f"[Step 30] Loaded MHRA orphan designations: current={n_current}, expired={n_expired}")


if __name__ == "__main__":
    # Only used if you run this step file directly
    run_step_30_load_mhra_orphan_register(
        current_csv_path=r"C:\path\to\Orphan_Register__3__current.csv",
        expired_csv_path=r"C:\path\to\Orphan_Register__3__expired.csv",
    )