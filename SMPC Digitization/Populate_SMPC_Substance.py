

"""
Populate_SMPC_Substance_Shortlist.py

Goal
----
For each SmPC (S2_Composition + S_6_1_excipients), generate a *high-quality shortlist*
of candidate substances from your SQL reference tables, ready to send to OpenAI for
cross-validation/association.

Key improvements vs earlier fuzzy-only approach
----------------------------------------------
1) Active substances (S2_Composition):
   - If Substance_Name_JSON exists for SmPC: use it as PRIMARY driver
     * check if each JSON item appears (loosely) in S2 text
     * exact match in preferred_name first, then exact in synonym name_text
     * remove matched big items from a working copy of S2
   - After JSON items: mine leftover S2 for meaningful residual terms (e.g. gentamicin, ovalbumin)
     and exact-match those.
   - Only if still nothing: fall back to a conservative "contains/INN" extractor + candidate shortlist.

2) Excipients (S_6_1_excipients):
   - Extract list-like terms
   - Exact match preferred/synonym first
   - If not found: fuzzy shortlist (RapidFuzz if installed) but on *term*, not whole paragraph

Outputs
-------
1) smpc_payloads.jsonl   - one JSON object per SmPC (machine-friendly for OpenAI batch)
2) smpc_term_candidates.csv - flat candidate list for inspection/debugging

Local env / .env
----------------
Place a .env at repo root (recommended) or pass env vars.
Required env vars:
  DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD
Optional:
  DB_DRIVER (default: ODBC Driver 17 for SQL Server)

Install deps
------------
pip install sqlalchemy pyodbc pandas python-dotenv rapidfuzz

Run
---
python Populate_SMPC_Substance_Shortlist.py
"""

import os
import re
import json
import unicodedata
from dataclasses import dataclass
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set

import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Optional fast fuzzy
try:
    from rapidfuzz import fuzz
    HAVE_RAPIDFUZZ = True
except Exception:
    import difflib
    HAVE_RAPIDFUZZ = False


# ----------------------------
# .env loading (repo root)
# ----------------------------
def load_env_if_needed():
    if os.getenv("DB_SERVER"):
        return
    # assume script sits inside a subfolder; repo root is one level up (adjust if needed)
    load_dotenv(r"C:\Users\anilp\OneDrive - digitecture.co.uk\Code\CV Managament_Github JS Code\CV_Management\.env")


# ----------------------------
# SQLAlchemy engine
# ----------------------------
def make_engine_from_env():
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER")
    db = os.getenv("DB_DATABASE")
    user = os.getenv("DB_USERNAME")
    pwd = os.getenv("DB_PASSWORD")

    if not all([server, db, user, pwd]):
        raise RuntimeError("Missing one or more DB env vars: DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD")

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


# ----------------------------
# Normalisation / tokenisation
# ----------------------------
PAREN_RE = re.compile(r"\([^)]*\)")
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s\-\/]")
WS_RE = re.compile(r"\s+")

STOP_TOKENS = {
    "and", "or", "with", "without", "of", "for", "in", "to", "by", "per",
    "each", "contains", "contain", "ml", "l", "mg", "mcg", "g", "%", "dose",
    "tablet", "tablets", "capsule", "capsules", "solution", "suspension",
    "injection", "infusion", "oral", "iv", "subcutaneous", "intravenous",
    "film", "coated", "powder", "concentrate", "drops", "cream", "ointment",
    "antibody", "immunoglobulin", "human", "mouse", "murine", "chimeric",
    "heavy", "light", "chain", "variable", "region", "igg1", "igg4",
    "monoclonal", "glycosylated", "mammalian", "chromatography",
    "purified", "produced", "culture", "cells", "cell", "chromatography",
    "including", "removal", "procedures", "full", "list", "see", "section"
}

def normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = s.lower()
    s = s.replace("’", "'")
    # remove parenthetical content for some checks; keep separate where needed
    s = PAREN_RE.sub(" ", s)
    s = NON_ALNUM_RE.sub(" ", s)
    s = WS_RE.sub(" ", s).strip()
    return s

def tokens(s: str) -> List[str]:
    s = normalize_text(s)
    toks = [t for t in s.split(" ") if t and t not in STOP_TOKENS and len(t) > 1]
    return toks


# ----------------------------
# Term extraction
# ----------------------------
BULLET_SPLIT_RE = re.compile(r"(?:\r?\n)+|•|·|;")

def extract_list_terms(section_text: str) -> List[str]:
    """Used mainly for S_6_1_excipients."""
    if not section_text:
        return []
    raw = section_text.replace("\t", " ")
    parts = BULLET_SPLIT_RE.split(raw)

    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "," in p and len(p) < 400:
            out.extend([x.strip() for x in p.split(",") if x.strip()])
        else:
            out.append(p)

    cleaned = []
    for t in out:
        t2 = t.strip(" -–—:.")
        if len(t2) < 3:
            continue
        t2 = re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|%)\b", " ", t2, flags=re.I)
        t2 = WS_RE.sub(" ", t2).strip()
        if t2:
            cleaned.append(t2)

    seen = set()
    uniq = []
    for t in cleaned:
        key = normalize_text(t)
        if key and key not in seen:
            seen.add(key)
            uniq.append(t)
    return uniq

def dedupe_by_substance_sk(rows: List[dict]) -> List[dict]:
    """
    Keep only the best candidate per (section_code, normalized term_text, substance_sk).
    Prefer:
      - higher local_conf_substance
      - exact/token_exact over fuzzy
      - preferred (synonym_id is None) over synonym
    """
    def rank(r):
        score = float(r.get("local_conf_substance") or 0.0)
        src = r.get("local_match_source", "")
        src_bonus = 0.2 if src in ("preferred", "synonym", "exact", "token_exact") else 0.0
        pref_bonus = 0.1 if r.get("synonym_id") is None else 0.0
        return score + src_bonus + pref_bonus

    best = {}
    for r in rows:
        key = (r["section_code"], normalize_text(r["term_text"]), r["substance_sk"])
        if key not in best or rank(r) > rank(best[key]):
            best[key] = r

    return list(best.values())

# Active substance extraction fallback (when no JSON)
CONTAINS_TOKEN_RE = re.compile(r"\bcontains\b.*?\b([a-z][a-z0-9\-]{2,})\b", re.I)
EACH_ML_RE = re.compile(r"\beach\s+(?:ml|mL)\s+contains\b.*?\b([a-z][a-z0-9\-]{2,})\b", re.I)
EACH_VIAL_RE = re.compile(r"\beach\s+vial\s+contains\b.*?\b([a-z][a-z0-9\-]{2,})\b", re.I)
WORD_RE = re.compile(r"\b[a-z][a-z0-9\-]{2,}\b", re.I)

def extract_active_terms_from_s2(s2_text: str) -> List[str]:
    """Conservative fallback: pulls likely INN tokens rather than whole paragraphs."""
    if not s2_text:
        return []
    s = s2_text

    hits: List[str] = []
    for rx in (EACH_ML_RE, EACH_VIAL_RE, CONTAINS_TOKEN_RE):
        for m in rx.finditer(s):
            hits.append(m.group(1))

    if not hits:
        # biologics often end with -mab; add more suffixes later if needed
        toks = WORD_RE.findall(s)
        hits = [t for t in toks if t.lower().endswith("mab")]

    out, seen = [], set()
    for h in hits:
        hn = normalize_text(h)
        if hn and hn not in seen:
            seen.add(hn)
            out.append(h)
    return out


# Residual mining in S2 after removing big strain strings
RESIDUES_RE = re.compile(r"\bresidues?\b.*?:\s*(.+?)(?:\.|$)", re.I)
PAREN_ITEMS_RE = re.compile(r"\((?:e\.g\.\s*)?([^)]+)\)", re.I)

def extract_residual_terms(s2_working: str) -> List[str]:
    if not s2_working:
        return []
    terms: List[str] = []

    m = RESIDUES_RE.search(s2_working)
    if m:
        chunk = m.group(1)
        parts = re.split(r",|\band\b", chunk, flags=re.I)
        for p in parts:
            p = p.strip(" ;:.-\n\t")
            if p:
                terms.append(p)

    for pm in PAREN_ITEMS_RE.finditer(s2_working):
        inside = pm.group(1)
        for p in re.split(r",|\band\b", inside, flags=re.I):
            p = p.strip(" ;:.-\n\t")
            if p:
                terms.append(p)

    # fallback: INN-ish tokens
    toks = tokens(s2_working)
    for t in toks:
        if t.endswith(("mab", "cin", "mycin", "vir", "navir", "caine")):
            terms.append(t)

    out, seen = [], set()
    for t in terms:
        tn = normalize_text(t)
        if tn and tn not in seen and len(tn) >= 3:
            seen.add(tn)
            out.append(t)
    return out


# ----------------------------
# Substance ref data structures
# ----------------------------
@dataclass
class NameRow:
    substance_sk: int
    sms_id: str
    preferred_name: str
    synonym_id: Optional[int]
    synonym: Optional[str]
    name_text: str          # preferred_name or synonym
    name_norm: str
    is_preferred: bool

@dataclass
class ExactHit:
    substance_sk: int
    synonym_id: Optional[int]
    match_source: str       # "preferred" | "synonym"
    rationale: str

def build_exact_indexes(name_rows: List[NameRow]):
    preferred_by_norm: Dict[str, int] = {}
    synonym_by_norm: Dict[str, Tuple[int, Optional[int]]] = {}
    # Also keep quick lookup for the "best display" names
    preferred_display: Dict[int, str] = {}

    for r in name_rows:
        if r.is_preferred and r.name_norm:
            preferred_by_norm.setdefault(r.name_norm, r.substance_sk)
            preferred_display.setdefault(r.substance_sk, r.preferred_name)

    for r in name_rows:
        if (not r.is_preferred) and r.name_norm:
            synonym_by_norm.setdefault(r.name_norm, (r.substance_sk, r.synonym_id))

    return preferred_by_norm, synonym_by_norm, preferred_display

def exact_lookup(term: str,
                 preferred_by_norm: Dict[str, int],
                 synonym_by_norm: Dict[str, Tuple[int, Optional[int]]]) -> Optional[ExactHit]:
    tn = normalize_text(term)
    if not tn:
        return None

    if tn in preferred_by_norm:
        return ExactHit(
            substance_sk=preferred_by_norm[tn],
            synonym_id=None,
            match_source="preferred",
            rationale="Exact match on Staging.Substance.preferred_name"
        )

    if tn in synonym_by_norm:
        sk, syn_id = synonym_by_norm[tn]
        return ExactHit(
            substance_sk=sk,
            synonym_id=syn_id,
            match_source="synonym",
            rationale="Exact match on Staging.Substance_Name.name_text"
        )

    return None


# ----------------------------
# "Loose contains" + removal for big JSON strain items
# ----------------------------
def loose_contains(haystack: str, needle: str) -> bool:
    h = normalize_text(haystack or "")
    n = normalize_text(needle or "")
    return bool(n) and n in h

def remove_term_from_text(work_text: str, term: str) -> str:
    if not work_text or not term:
        return work_text
    t = term.strip()
    pattern = re.escape(t)
    pattern = pattern.replace(r"\ ", r"\s+")
    pattern = pattern.replace(r"\-", r"[-\s]*")
    pattern = pattern.replace(r"\/", r"[\/\s]*")
    return re.sub(pattern, " ", work_text, flags=re.IGNORECASE)


# ----------------------------
# Fuzzy shortlist (only used when exact not found)
# ----------------------------
class FuzzyShortlister:
    def __init__(self, name_rows: List[NameRow]):
        self.name_rows = name_rows
        self.exact_map: Dict[str, List[int]] = defaultdict(list)
        self.inv: Dict[str, List[int]] = defaultdict(list)
        self.df: Counter = Counter()

        for i, r in enumerate(name_rows):
            if not r.name_norm:
                continue
            self.exact_map[r.name_norm].append(i)
            toks = set(tokens(r.name_norm))
            for tk in toks:
                self.inv[tk].append(i)
                self.df[tk] += 1

    def _pool(self, query: str, max_pool: int = 4000) -> List[int]:
        qn = normalize_text(query)
        if not qn:
            return []
        if qn in self.exact_map:
            return self.exact_map[qn][:]
        qtoks = list(set(tokens(qn)))
        if not qtoks:
            return []
        qtoks.sort(key=lambda t: self.df.get(t, 10**9))
        pool: Set[int] = set()
        for tk in qtoks[:6]:
            for idx in self.inv.get(tk, []):
                pool.add(idx)
                if len(pool) >= max_pool:
                    break
            if len(pool) >= max_pool:
                break
        return list(pool)

    def shortlist(self, query: str, top_k: int = 15) -> List[Tuple[NameRow, float]]:
        qn = normalize_text(query)
        if not qn:
            return []

        # exact full query
        if qn in self.exact_map:
            out = []
            for idx in self.exact_map[qn][:top_k]:
                out.append((self.name_rows[idx], 1.0))
            return out

        pool = self._pool(query)
        if not pool:
            return []

        scored = []
        if HAVE_RAPIDFUZZ:
            for idx in pool:
                s = fuzz.token_set_ratio(qn, self.name_rows[idx].name_norm) / 100.0
                scored.append((idx, float(s)))
        else:
            for idx in pool:
                s = difflib.SequenceMatcher(None, qn, self.name_rows[idx].name_norm).ratio()
                scored.append((idx, float(s)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self.name_rows[i], s) for i, s in scored[:top_k]]


# ----------------------------
# SQL loaders (your queries, lightly structured)
# ----------------------------
def load_substances(engine) -> List[NameRow]:
    sql = """
    SELECT distinct
        s.substance_sk,
        s.SMS_ID,
        s.preferred_name,
        sn.substance_name_sk as synonym_id,
        sn.name_text as synonym
    FROM Staging.Substance s
    INNER JOIN Staging.Substance_Name sn
        ON sn.sms_id = s.sms_id
    """
    df = pd.read_sql(sql, engine)

    rows: List[NameRow] = []

    # preferred name rows
    pref_df = df[["substance_sk", "SMS_ID", "preferred_name"]].drop_duplicates("substance_sk")
    for r in pref_df.itertuples(index=False):
        pn = "" if r.preferred_name is None else str(r.preferred_name)
        rows.append(NameRow(
            substance_sk=int(r.substance_sk),
            sms_id="" if r.SMS_ID is None else str(r.SMS_ID),
            preferred_name=pn,
            synonym_id=None,
            synonym=None,
            name_text=pn,
            name_norm=normalize_text(pn),
            is_preferred=True
        ))

    # synonym rows
    for r in df.itertuples(index=False):
        syn = "" if r.synonym is None else str(r.synonym)
        if not syn.strip():
            continue
        rows.append(NameRow(
            substance_sk=int(r.substance_sk),
            sms_id="" if r.SMS_ID is None else str(r.SMS_ID),
            preferred_name="" if r.preferred_name is None else str(r.preferred_name),
            synonym_id=None if r.synonym_id is None else int(r.synonym_id),
            synonym=syn,
            name_text=syn,
            name_norm=normalize_text(syn),
            is_preferred=False
        ))

    rows = [r for r in rows if r.name_norm]
    return rows


def load_smpc_core(engine) -> pd.DataFrame:
    # You can keep your filter; I left it as-is
    sql = """
    SELECT
        id as smpc_id,
        S1_Name_of_Medicinal_product as product_name,
        S2_Composition,
        S_6_1_excipients
    FROM Staging.SMPC
    WHERE id NOT IN (SELECT DISTINCT SMPC_id FROM Staging.SMPC_Active_Substance)
      AND id > 150
    """
    return pd.read_sql(sql, engine)


def load_smpc_substance_json(engine) -> pd.DataFrame:
    # Joined source: S2 + meta JSON
    sql = """
    SELECT
        s.id as smpc_id,
        s.S2_Composition,
        mt.Substance_Name_JSON
    FROM Staging.SMPC s
    INNER JOIN Staging.SMPC_Meta_data mt
        ON mt.SMPC_ID = s.id
    """
    return pd.read_sql(sql, engine)


# ----------------------------
# Candidate building
# ----------------------------
def parse_substance_json(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return []
        try:
            arr = json.loads(v)
            if isinstance(arr, list):
                return [str(x) for x in arr if str(x).strip()]
        except Exception:
            # not valid JSON; ignore
            return []
    return []


def build_active_candidates(
    smpc_id: int,
    s2_text: str,
    substance_json_items: List[str],
    preferred_by_norm: Dict[str, int],
    synonym_by_norm: Dict[str, Tuple[int, Optional[int]]],
    preferred_display: Dict[int, str],
    fuzzy: FuzzyShortlister,
    fuzzy_top_k: int = 10,
    fuzzy_min_score: float = 0.82
):
    """
    Returns:
      candidates: list of dicts (for payload + csv)
      s2_remaining: working copy after removals
      extracted_terms: list of terms used as inputs
    """
    candidates = []
    work = s2_text or ""
    extracted_terms: List[str] = []

    # A) JSON-driven exact matching (preferred then synonym)
    for raw in substance_json_items:
        if not raw or not raw.strip():
            continue
        extracted_terms.append(raw)

        if not loose_contains(s2_text, raw):
            continue

        hit = exact_lookup(raw, preferred_by_norm, synonym_by_norm)
        if hit:
            candidates.append({
                "smpc_id": smpc_id,
                "section_code": "S_2",
                "term_text": raw,
                "role_suggested": "Active",
                "substance_sk": hit.substance_sk,
                "preferred_name": preferred_display.get(hit.substance_sk),
                "synonym_id": hit.synonym_id,
                "local_conf_substance": 1.0,
                "local_rationale_substance": hit.rationale,
                "local_conf_synonym": 1.0 if hit.match_source == "synonym" else None,
                "local_rationale_synonym": hit.rationale if hit.match_source == "synonym" else None,
                "local_match_source": hit.match_source,
            })
            work = remove_term_from_text(work, raw)

    # B) Residual exact matching (e.g. gentamicin, ovalbumin)
    residual_terms = extract_residual_terms(work)
    for term in residual_terms:
        extracted_terms.append(term)
        hit = exact_lookup(term, preferred_by_norm, synonym_by_norm)
        if hit:
            candidates.append({
                "smpc_id": smpc_id,
                "section_code": "S_2",
                "term_text": term,
                "role_suggested": "Active",  # change to "Residue" if you want a separate label
                "substance_sk": hit.substance_sk,
                "preferred_name": preferred_display.get(hit.substance_sk),
                "synonym_id": hit.synonym_id,
                "local_conf_substance": 1.0,
                "local_rationale_substance": f"{hit.rationale} (residual S2)",
                "local_conf_synonym": 1.0 if hit.match_source == "synonym" else None,
                "local_rationale_synonym": hit.rationale if hit.match_source == "synonym" else None,
                "local_match_source": hit.match_source,
            })

    # C) If still empty, fallback extractors + fuzzy shortlist (term-level, not paragraph-level)
    if not candidates:
        fallback_terms = extract_active_terms_from_s2(s2_text)
        for term in fallback_terms:
            extracted_terms.append(term)
            hit = exact_lookup(term, preferred_by_norm, synonym_by_norm)
            if hit:
                candidates.append({
                    "smpc_id": smpc_id,
                    "section_code": "S_2",
                    "term_text": term,
                    "role_suggested": "Active",
                    "substance_sk": hit.substance_sk,
                    "preferred_name": preferred_display.get(hit.substance_sk),
                    "synonym_id": hit.synonym_id,
                    "local_conf_substance": 1.0,
                    "local_rationale_substance": hit.rationale,
                    "local_conf_synonym": 1.0 if hit.match_source == "synonym" else None,
                    "local_rationale_synonym": hit.rationale if hit.match_source == "synonym" else None,
                    "local_match_source": hit.match_source,
                })
            else:
                # fuzzy suggestions for OpenAI cross-check
                for nr, score in fuzzy.shortlist(term, top_k=fuzzy_top_k):
                    if score < fuzzy_min_score:
                        continue
                    candidates.append({
                        "smpc_id": smpc_id,
                        "section_code": "S_2",
                        "term_text": term,
                        "role_suggested": "Active",
                        "substance_sk": nr.substance_sk,
                        "preferred_name": preferred_display.get(nr.substance_sk, nr.preferred_name),
                        "synonym_id": nr.synonym_id if not nr.is_preferred else None,
                        "local_conf_substance": round(score, 4),
                        "local_rationale_substance": "Fuzzy shortlist (fallback)",
                        "local_conf_synonym": round(score, 4) if not nr.is_preferred else None,
                        "local_rationale_synonym": "Fuzzy shortlist (fallback)" if not nr.is_preferred else None,
                        "local_match_source": "fuzzy",
                    })

    # de-dup by (substance_sk, synonym_id, term_text)
    seen = set()
    uniq = []
    for c in candidates:
        k = (c["substance_sk"], c.get("synonym_id"), normalize_text(c["term_text"]))
        if k not in seen:
            seen.add(k)
            uniq.append(c)

    uniq = dedupe_by_substance_sk(candidates)
    return uniq, work, extracted_terms


def build_excipient_candidates(
    smpc_id: int,
    s6_1_text: str,
    preferred_by_norm: Dict[str, int],
    synonym_by_norm: Dict[str, Tuple[int, Optional[int]]],
    preferred_display: Dict[int, str],
    fuzzy: FuzzyShortlister,
    fuzzy_top_k: int = 10,
    fuzzy_min_score: float = 0.84
):
    candidates = []
    terms = extract_list_terms(s6_1_text)

    for term in terms:
        hit = exact_lookup(term, preferred_by_norm, synonym_by_norm)
        if hit:
            candidates.append({
                "smpc_id": smpc_id,
                "section_code": "S_6_1",
                "term_text": term,
                "role_suggested": "Excipient",
                "substance_sk": hit.substance_sk,
                "preferred_name": preferred_display.get(hit.substance_sk),
                "synonym_id": hit.synonym_id,
                "local_conf_substance": 1.0,
                "local_rationale_substance": hit.rationale,
                "local_conf_synonym": 1.0 if hit.match_source == "synonym" else None,
                "local_rationale_synonym": hit.rationale if hit.match_source == "synonym" else None,
                "local_match_source": hit.match_source,
            })
        else:
            # fuzzy shortlist (term-level)
            for nr, score in fuzzy.shortlist(term, top_k=fuzzy_top_k):
                if score < fuzzy_min_score:
                    continue
                candidates.append({
                    "smpc_id": smpc_id,
                    "section_code": "S_6_1",
                    "term_text": term,
                    "role_suggested": "Excipient",
                    "substance_sk": nr.substance_sk,
                    "preferred_name": preferred_display.get(nr.substance_sk, nr.preferred_name),
                    "synonym_id": nr.synonym_id if not nr.is_preferred else None,
                    "local_conf_substance": round(score, 4),
                    "local_rationale_substance": "Fuzzy shortlist (excipient term)",
                    "local_conf_synonym": round(score, 4) if not nr.is_preferred else None,
                    "local_rationale_synonym": "Fuzzy shortlist (excipient term)" if not nr.is_preferred else None,
                    "local_match_source": "fuzzy",
                })

    # de-dup
    seen = set()
    uniq = []
    for c in candidates:
        k = (c["substance_sk"], c.get("synonym_id"), normalize_text(c["term_text"]), c["section_code"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)

    uniq = dedupe_by_substance_sk(uniq)
    return uniq, terms


# ----------------------------
# Main
# ----------------------------
def main():
    load_env_if_needed()
    engine = make_engine_from_env()

    print("Loading reference substances (preferred + synonyms)...")
    name_rows = load_substances(engine)
    print(f"Loaded name rows: {len(name_rows):,}")

    preferred_by_norm, synonym_by_norm, preferred_display = build_exact_indexes(name_rows)
    fuzzy = FuzzyShortlister(name_rows)

    print("Loading SmPC core rows to process...")
    smpc_df = load_smpc_core(engine)
    print(f"Loaded SmPCs to process: {len(smpc_df):,}")

    print("Loading SmPC Substance_Name_JSON (where available)...")
    json_df = load_smpc_substance_json(engine)
    # Map smpc_id -> JSON list
    json_map: Dict[int, List[str]] = {}
    for r in json_df.itertuples(index=False):
        json_map[int(r.smpc_id)] = parse_substance_json(getattr(r, "Substance_Name_JSON"))

    payload_lines: List[str] = []
    flat_rows: List[dict] = []

    for r in smpc_df.itertuples(index=False):
        smpc_id = int(r.smpc_id)
        product_name = "" if r.product_name is None else str(r.product_name)
        s2_text = "" if r.S2_Composition is None else str(r.S2_Composition)
        s6_1_text = "" if r.S_6_1_excipients is None else str(r.S_6_1_excipients)

        substance_json_items = json_map.get(smpc_id, [])

        active_cands, s2_remaining, s2_terms_used = build_active_candidates(
            smpc_id=smpc_id,
            s2_text=s2_text,
            substance_json_items=substance_json_items,
            preferred_by_norm=preferred_by_norm,
            synonym_by_norm=synonym_by_norm,
            preferred_display=preferred_display,
            fuzzy=fuzzy
        )

        excip_cands, s6_terms = build_excipient_candidates(
            smpc_id=smpc_id,
            s6_1_text=s6_1_text,
            preferred_by_norm=preferred_by_norm,
            synonym_by_norm=synonym_by_norm,
            preferred_display=preferred_display,
            fuzzy=fuzzy
        )

        all_cands = active_cands + excip_cands
        flat_rows.extend(all_cands)

        payload = {
            "smpc_id": smpc_id,
            "product_name": product_name,
            "sections": {
                "S2_Composition": s2_text,
                "S_6_1_excipients": s6_1_text
            },
            "inputs_used": {
                "Substance_Name_JSON": substance_json_items,
                "S2_terms_used": s2_terms_used,
                "S2_remaining_after_json_removal": s2_remaining,
                "S6_1_terms_extracted": s6_terms
            },
            "candidate_substances": [
                {
                    "substance_sk": c["substance_sk"],
                    "preferred_name": c.get("preferred_name"),
                    "synonym_id": c.get("synonym_id"),
                    "section_code": c["section_code"],
                    "role_suggested": c["role_suggested"],
                    "term_text": c["term_text"],
                    "local_conf_substance": c["local_conf_substance"],
                    "local_rationale_substance": c["local_rationale_substance"],
                    "local_conf_synonym": c.get("local_conf_synonym"),
                    "local_rationale_synonym": c.get("local_rationale_synonym"),
                    "local_match_source": c["local_match_source"],
                }
                for c in all_cands
            ],
            "expected_openai_response_fields": [
                "SMPC_ID",
                "substance_sk",
                "role (Active | Excipient | Excipient_with_special_role)",
                "Synonym_id (only if SmPC term doesn't match preferred)",
                "confidence_substance_match",
                "rationale_substance_match",
                "confidence_synonym_match",
                "rationale_synonym_match",
                "model_used"
            ]
        }

        payload_lines.append(json.dumps(payload, ensure_ascii=False))

    out_jsonl = "smpc_payloads.jsonl"
    out_csv = "smpc_term_candidates.csv"

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for line in payload_lines:
            f.write(line + "\n")

    pd.DataFrame(flat_rows).to_csv(out_csv, index=False, encoding="utf-8-sig")

    print(f"Written: {out_jsonl}")
    print(f"Written: {out_csv}")
    print("Done.")


if __name__ == "__main__":
    main()