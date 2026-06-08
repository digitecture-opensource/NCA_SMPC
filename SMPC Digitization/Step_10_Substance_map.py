# Step_10_Subsance_map.py
"""
Step 10 - Substance mapping (pipeline-compatible)

- Provides: run_step_10_substance_map(...) for orchestration (run_pipeline.py)
- Still runnable standalone (python Step_10_Subsance_map.py)
- Fixes transaction usage (no conn.commit() inside engine.begin())
- Keeps your Structured Outputs json_schema usage (text.format.name etc.)
"""

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

from openai import OpenAI


# ----------------------------
# Config defaults
# ----------------------------
DEFAULT_INPUT_JSONL = os.getenv("SMPC_PAYLOADS_JSONL", "smpc_payloads.jsonl")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
DEFAULT_SLEEP_SECONDS = float(os.getenv("SLEEP_BETWEEN_CALLS_SEC", "0") or "0")


# ----------------------------
# OpenAI prompt + schema
# ----------------------------
SYSTEM_PROMPT = """You validate SmPC substance coding.
Use the candidate_substances provided (IDs + names + section + role suggestions + local confidence).
Return final confirmed mappings as JSON using the required schema.

Rules:
- Do not invent substance_sk or synonym_id: pick from provided candidates only.
- One mapping per substance_sk (deduplicate).
- role must be one of: Active, Excipient, Excipient_with_special_role.
- synonym_id should be null if the preferred name matches; set it only when the matched term is clearly a synonym row.
- If unsure between candidates, choose the best and lower confidence, explain rationale briefly.
- Return ALL distinct substances found in the composition text that match candidates, even if multiple have the same role (e.g. two Active substances in a combination product).
"""

RESPONSE_SCHEMA = {
    "name": "smpc_substance_mapping",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "smpc_id": {"type": "integer"},
            "product_name": {"type": "string"},
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "substance_sk": {"type": "integer"},
                        "role": {
                            "type": "string",
                            "enum": ["Active", "Excipient", "Excipient_with_special_role"],
                        },
                        "synonym_id": {"type": ["integer", "null"]},
                        "confidence_substance_match": {"type": "number"},
                        "rationale_substance_match": {"type": "string"},
                        "confidence_synonym_match": {"type": ["number", "null"]},
                        "rationale_synonym_match": {"type": ["string", "null"]},
                        "model_used": {"type": "string"},
                    },
                    "required": [
                        "substance_sk",
                        "role",
                        "synonym_id",
                        "confidence_substance_match",
                        "rationale_substance_match",
                        "confidence_synonym_match",
                        "rationale_synonym_match",
                        "model_used",
                    ],
                },
            },
        },
        "required": ["smpc_id", "product_name", "mappings"],
    },
}


def build_user_prompt(payload: Dict[str, Any]) -> str:
    smpc_id = payload["smpc_id"]
    product_name = payload.get("product_name", "")

    sections = payload.get("sections", {})
    s2 = sections.get("S2_Composition", payload.get("S2", "")) or ""
    s6 = sections.get("S_6_1_excipients", payload.get("S6_1", "")) or ""

    candidates = payload.get("candidate_substances", []) or []

    return f"""SmPC_ID: {smpc_id}
Product: {product_name}

Section 2 (Composition):
{s2}

Section 6.1 (Excipients):
{s6}

Candidate_substances (choose from these only; do NOT invent IDs):
{json.dumps(candidates, ensure_ascii=False)}

Return confirmed mappings in the required JSON schema.
"""


# ----------------------------
# Env loading
# ----------------------------
def load_env_if_needed():
    """
    Loads .env once if DB vars are not already present.
    Tries repo root (../.env), then your known absolute path.
    """
    if os.getenv("DB_SERVER") and os.getenv("DB_DATABASE") and os.getenv("DB_USERNAME") and os.getenv("DB_PASSWORD"):
        return

    # Try repo root relative to this file
    here = Path(__file__).resolve()
    repo_env = here.parent.parent / ".env"
    if repo_env.exists():
        load_dotenv(repo_env)
        return

    # Fallback to your previous absolute path
    fallback = Path(r"C:\Users\anilp\OneDrive - digitecture.co.uk\Code\CV Managament_Github JS Code\CV_Management\.env")
    if fallback.exists():
        load_dotenv(fallback)


# ----------------------------
# DB engine + SQL
# ----------------------------
def make_engine_from_env():
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER")
    db = os.getenv("DB_DATABASE")
    user = os.getenv("DB_USERNAME")
    pwd = os.getenv("DB_PASSWORD")

    if not all([server, db, user, pwd]):
        raise RuntimeError("Missing DB env vars: DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD")

    params = f"""
    Driver={{{driver}}};
    Server={server};
    Database={db};
    UID={user};
    PWD={pwd};
    Encrypt=yes;
    TrustServerCertificate=no;
    Connection Timeout=30;
    """
    conn_str = f"mssql+pyodbc:///?odbc_connect={quote_plus(params)}"
    return create_engine(conn_str, fast_executemany=True)


CLEAR_CURRENT_SQL = """
UPDATE [Staging].[SMPC_Active_Substance]
SET current_flag = 0
WHERE SMPC_id = :smpc_id AND current_flag = 1;
"""

INSERT_SQL = """
INSERT INTO [Staging].[SMPC_Active_Substance] (
    SMPC_id,
    Substance_sk,
    Substance_role,
    current_flag,
    Synonym_id,
    confidence_substance_match,
    rationale_substance_match,
    confidence_synonym_match,
    rationale_synonym_match,
    model_used
)
VALUES (
    :SMPC_id,
    :Substance_sk,
    :Substance_role,
    :current_flag,
    :Synonym_id,
    :confidence_substance_match,
    :rationale_substance_match,
    :confidence_synonym_match,
    :rationale_synonym_match,
    :model_used
);
"""


# ----------------------------
# Helpers
# ----------------------------
def clamp_0_1_decimal_5_4(x: Any) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    if v < 0:
        v = 0.0
    if v > 1:
        v = 1.0
    return round(v, 4)


def truncate(s: Optional[str], max_len: int) -> Optional[str]:
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= max_len else s[:max_len]


def dedupe_by_substance_sk(mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensures one mapping per substance_sk by keeping the highest confidence_substance_match.
    """
    best: Dict[int, Dict[str, Any]] = {}
    for m in mappings or []:
        if m.get("substance_sk") is None:
            continue
        sk = int(m["substance_sk"])
        conf = clamp_0_1_decimal_5_4(m.get("confidence_substance_match"))
        if sk not in best or conf > clamp_0_1_decimal_5_4(best[sk].get("confidence_substance_match")):
            best[sk] = m
    return list(best.values())


def to_insert_params(smpc_id: int, mapping: Dict[str, Any], model_used_default: str) -> Dict[str, Any]:
    # Force model_used to be the actual model called
    model_used = truncate(model_used_default, 100)

    syn_id = mapping.get("synonym_id")
    syn_id = int(syn_id) if syn_id is not None else None

    return {
        "SMPC_id": smpc_id,
        "Substance_sk": int(mapping["substance_sk"]),
        "Substance_role": truncate(mapping.get("role"), 250),
        "current_flag": 1,
        "Synonym_id": syn_id,
        "confidence_substance_match": clamp_0_1_decimal_5_4(mapping.get("confidence_substance_match")),
        "rationale_substance_match": truncate(mapping.get("rationale_substance_match"), 2000),
        "confidence_synonym_match": None
        if mapping.get("confidence_synonym_match") is None
        else clamp_0_1_decimal_5_4(mapping.get("confidence_synonym_match")),
        "rationale_synonym_match": truncate(mapping.get("rationale_synonym_match"), 2000),
        "model_used": model_used,
    }


# ----------------------------
# OpenAI call
# ----------------------------
def call_openai_for_one(payload: Dict[str, Any], client: OpenAI, model: str) -> Dict[str, Any]:
    user_prompt = build_user_prompt(payload)

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "smpc_substance_mapping",
                "strict": True,
                "schema": RESPONSE_SCHEMA["schema"],
            }
        },
    )

    # Hardened extraction (prevents NoneType iteration)
    output = getattr(resp, "output", None) or []
    for item in output:
        content = getattr(item, "content", None) or []
        for c in content:
            if getattr(c, "type", None) == "output_text" and getattr(c, "text", None):
                return json.loads(c.text)

    raise RuntimeError(f"No output_text returned. resp.id={getattr(resp,'id',None)} resp.output={output}")


# ----------------------------
# Callable step for run_pipeline.py
# ----------------------------
def run_step_10_substance_map(
    input_jsonl: str = DEFAULT_INPUT_JSONL,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    only_smpc_ids: Optional[set[int]] = None,
    sleep_between_calls_sec: float = DEFAULT_SLEEP_SECONDS,
) -> Dict[str, int]:
    """
    Reads smpc_payloads.jsonl, calls OpenAI, inserts confirmed mappings into Staging.SMPC_Active_Substance.

    Returns: {"processed": int, "inserted_rows": int, "failed": int}
    """
    load_env_if_needed()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

    engine = make_engine_from_env()
    oai = OpenAI()

    processed = 0
    inserted_rows = 0
    failed = 0

    with open(input_jsonl, "r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            if not line.strip():
                continue

            payload = json.loads(line)
            smpc_id = int(payload.get("smpc_id"))

            if only_smpc_ids and smpc_id not in only_smpc_ids:
                continue

            try:
                result = call_openai_for_one(payload, oai, model=model)

                result_smpc_id = int(result["smpc_id"])
                if result_smpc_id != smpc_id:
                    raise RuntimeError(f"SmPC id mismatch: payload={smpc_id} response={result_smpc_id}")

                mappings = result.get("mappings", [])
                if not isinstance(mappings, list):
                    raise RuntimeError("mappings is not a list")

                mappings = dedupe_by_substance_sk(mappings)

                if dry_run:
                    print(f"[DRY_RUN] SMPC {smpc_id}: {len(mappings)} mapping(s)")
                else:
                    # ✅ One transaction per SMPC (no manual commit)
                    with engine.begin() as conn:
                        conn.execute(text(CLEAR_CURRENT_SQL), {"smpc_id": smpc_id})
                        for m in mappings:
                            conn.execute(text(INSERT_SQL), to_insert_params(smpc_id, m, model_used_default=model))
                            inserted_rows += 1

                processed += 1
                if processed % 20 == 0:
                    print(f"Processed {processed} SMPCs so far...")
                if sleep_between_calls_sec:
                    time.sleep(sleep_between_calls_sec)

            except Exception as e:
                failed += 1
                print(f"[ERROR] line {line_no} smpc_id={smpc_id}: {e}")

    return {"processed": processed, "inserted_rows": inserted_rows, "failed": failed}


# ----------------------------
# Standalone CLI wrapper (still works)
# ----------------------------
def main():
    only_ids_env = os.getenv("ONLY_SMPC_IDS", "").strip()
    only_smpc_ids = None
    if only_ids_env:
        only_smpc_ids = {int(x.strip()) for x in only_ids_env.split(",") if x.strip()}
    print (os.getenv("SMPC_PAYLOADS_JSONL", DEFAULT_INPUT_JSONL))
    stats = run_step_10_substance_map(
        input_jsonl=os.getenv("SMPC_PAYLOADS_JSONL", DEFAULT_INPUT_JSONL),    
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        dry_run=os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes"),
        only_smpc_ids=only_smpc_ids,
        sleep_between_calls_sec=float(os.getenv("SLEEP_BETWEEN_CALLS_SEC", DEFAULT_SLEEP_SECONDS)),
    )
    print(f"Step 10 complete: {stats}")


if __name__ == "__main__":
    main()