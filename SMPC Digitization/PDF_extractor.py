import azure.functions as func
import datetime
import json
import logging
import os, sys
import tempfile
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from pathlib import Path
from dotenv import load_dotenv
import fitz  # PyMuPDF
import re
from dateutil import parser
import headers  # your headers.py file with section header lists
import glob

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = func.FunctionApp()

# SQL Server config — all values from environment, no hardcoded credentials
username = os.getenv("DB_USERNAME")
password = os.getenv("DB_PASSWORD")
server   = os.getenv("DB_SERVER")
database = os.getenv("DB_DATABASE")
driver   = os.getenv("DRIVER", "ODBC Driver 18 for SQL Server")

params = f"""
    Driver={{{driver}}};
    Server={server};
    Database={database};
    UID={username};
    PWD={password};
    Encrypt=yes;
    TrustServerCertificate=no;
    Connection Timeout=30;
"""
sql_conn_str = create_engine(f"mssql+pyodbc:///?odbc_connect={quote_plus(params)}")

#print ("Headers loaded from headers.py. All headers known:", len(hdrs.ALL_KNOWN_HEADERS))

# Helpers
def parse_date_safe(value):
    try:
        parsed = parser.parse(value, dayfirst=True)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None

DOC_HEADING_RE = re.compile(r"\b\d{1,2}(?:\.\d{1,2})?\s+[A-Z][A-Z ]{4,60}\b")

def warn_unknown_headings(text: str, known_headers: set, source_name: str = ""):
    found = DOC_HEADING_RE.findall(text)
    found_norm = {f.strip().upper() for f in found}

    unknown = sorted(h for h in found_norm if h not in known_headers)
    if unknown:
        print(f"WARNING: Unknown headings in {source_name or 'document'}:")
        for h in unknown:
            print("  -", h)

def normalize_text(text):
    return re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()

def clean_authotisation_text(text):
    text = normalize_text(text)
    match = re.search(r"(PL\s*\d+/\d+)", text)
    matchs = re.search(r"(PLGB?\s*\d+/\d+)", text)
    if matchs:
        return matchs.group(1).strip()
    if match:
        return match.group(1).strip()
    return text.strip()

def headers_to_regex(headers: list[str]) -> str:
    # escape each literal header and join with OR
    escaped = [re.escape(h.strip()) for h in headers if h and h.strip()]
    return r"(?:%s)" % "|".join(escaped) if escaped else r"(?!x)x"  # never match if empty

#def extract_section_regex(text, start_pattern, end_pattern=None):
#    try:
#        start_match = re.search(start_pattern, text, re.IGNORECASE)
#        if not start_match:
#            print ("**Error**: No match for start pattern:", start_pattern)
    #         return ("", text)
    #     start_idx = start_match.end()
    #     end_idx = len(text)
    #     if end_pattern:
    #         end_match = re.search(end_pattern, text[start_idx:], re.IGNORECASE)
    #         if end_match:
    #             end_idx = start_idx + end_match.start()
                
    #     section_text = text[start_idx:end_idx].strip()
    #     section_text= re.sub(r"\s+\b(\d{1,2})\b\s*[\.\-:]?\s*$", "", section_text).strip()
        
    #     remainder_text = text[end_idx:].strip()    
    #     return  ( section_text, remainder_text )
    # except Exception as e:
    #     print(f"Error extracting section: {e}")
    #     return ("", text)

def extract_section_regex(text, start_headers, end_headers=None):
    """
    start_headers: list[str] OR regex string
    end_headers: list[str] OR regex string OR None
    Returns: (section_text, remainder_text)
    """
    try:
        start_pattern = headers_to_regex(start_headers) if isinstance(start_headers, list) else start_headers
        end_pattern = headers_to_regex(end_headers) if isinstance(end_headers, list) else end_headers
        
        #print ("Processing extract_section_regex with start_pattern:", start_pattern)

        start_match = re.search(start_pattern, text, re.IGNORECASE)
        if not start_match:
            print("**Error**: No match for start:", start_pattern)
            return ("", text)

        start_idx = start_match.end()
        end_idx = len(text)

        if end_pattern:
            end_match = re.search(end_pattern, text[start_idx:], re.IGNORECASE)
            #print ("end_match:", end_match)
            if end_match:
                end_idx = start_idx + end_match.start()

        section_text = text[start_idx:end_idx].strip()
        remainder_text = text[end_idx:].strip()
        #print ("Extracted section:", section_text)
        return (section_text, remainder_text)

    except Exception as e:
        print(f"Error extracting section: {e}")
        return ("", text)
def strip_known_headers(text: str, headers: list[str]) -> str:
    if not text:
        return ""
    s = text.strip()

    # Remove headers if they appear at the beginning (common PDF artifact)
    # Do this repeatedly because sometimes both "1" and "NAME..." appear.
    changed = True
    while changed:
        changed = False
        for h in sorted(headers, key=len, reverse=True):
            h_esc = re.escape(h.strip())
            new_s = re.sub(rf"^\s*{h_esc}\s*", "", s, flags=re.IGNORECASE).strip()
            if new_s != s:
                s = new_s
                changed = True
                break

    # Also remove the header phrase if it appears in-line as a repeated banner
    for h in sorted(headers, key=len, reverse=True):
        h_esc = re.escape(h.strip())
        s = re.sub(rf"\s*{h_esc}\s*", " ", s, flags=re.IGNORECASE)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_extracted_text(text):
    text = normalize_text(text)

    # Remove trailing section numbers (e.g. "Section Title 1.1", "Example 2")
    #text = re.sub(r"\s*\b\d+(\.\d+)?\b\s*$", "", text)

    # Also remove trailing section numbers if followed by punctuation (e.g. "Title 2.1.")
    #text = re.sub(r"\s*\b\d+(\.\d+)?[\.\-:]?\s*$", "", text)

    # Remove known section headings if included at end
    text = re.sub(
        r"\s*(PHARMACEUTICAL FORM|CLINICAL PARTICULARS|THERAPEUTIC INDICATIONS|CONTRAINDICATIONS|WARNINGS AND PRECAUTIONS|INTERACTION.*?|PREGNANCY AND LACTATION|OVERDOSE|PHARMACODYNAMIC|PHARMACOKINETIC|PRECLINICAL DATA|EXCIPIENTS|STORAGE|DISPOSAL|MARKETING AUTHORISATION HOLDER|NUMBER|REVISION OF THE TEXT)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )
    return text.strip()
   
   
def process_pdf(pdf_path):
    #print ("into ProcesS_pdf")
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    text = normalize_text(text)
    warn_unknown_headings(text, headers.ALL_KNOWN_HEADERS, os.path.basename(pdf_path))
    
    s1_text, remaining_text = extract_section_regex(text, headers.S1_HEADERS, headers.S2_HEADERS)

    # Clean section 1 so it doesn't contain header junk
    s1_text = strip_known_headers(s1_text, headers.S1_HEADERS + headers.S2_HEADERS)
    s1_text = clean_extracted_text(s1_text)
    
    s2_text, remaining_text = extract_section_regex(remaining_text, headers.S2_HEADERS, headers.S3_HEADERS)
    s2_text = strip_known_headers(s2_text, headers.S2_HEADERS + headers.S3_HEADERS)
    s2_text = clean_extracted_text(s2_text)
    
    s3_Pharmaceutical_form, remaining_text = extract_section_regex(    remaining_text,    headers.S3_HEADERS, headers.S4_1_HEADERS)
    s3_Pharmaceutical_form = strip_known_headers(s3_Pharmaceutical_form, headers.S3_HEADERS + headers.S4_1_HEADERS+headers.S4_HEADERS)
    s3_Pharmaceutical_form = clean_extracted_text(s3_Pharmaceutical_form)
    
    S_4_1_therapeutic_indications, remaining_text = extract_section_regex(    remaining_text,    headers.S4_1_HEADERS, headers.S4_2_HEADERS)
    S_4_1_therapeutic_indications = strip_known_headers(S_4_1_therapeutic_indications, headers.S4_1_HEADERS + headers.S4_2_HEADERS)
    S_4_1_therapeutic_indications = clean_extracted_text(S_4_1_therapeutic_indications)
    
    
    
    S_4_2_posology_administration, remaining_text = extract_section_regex(    remaining_text,    headers.S4_2_HEADERS, headers.S4_3_HEADERS)
    S_4_2_posology_administration = strip_known_headers(S_4_2_posology_administration, headers.S4_2_HEADERS + headers.S4_3_HEADERS)
    S_4_2_posology_administration = clean_extracted_text(S_4_2_posology_administration)
    
    S_4_3_contraindications, remaining_text = extract_section_regex(    remaining_text,    headers.S4_3_HEADERS, headers.S4_4_HEADERS)
    S_4_3_contraindications = strip_known_headers(S_4_3_contraindications, headers.S4_3_HEADERS + headers.S4_4_HEADERS)
    S_4_3_contraindications = clean_extracted_text(S_4_3_contraindications)

    S_4_4_warnings_precautions, remaining_text = extract_section_regex(    remaining_text,    headers.S4_4_HEADERS, headers.S4_5_HEADERS)
    S_4_4_warnings_precautions = strip_known_headers(S_4_4_warnings_precautions, headers.S4_4_HEADERS + headers.S4_5_HEADERS)
    S_4_4_warnings_precautions = clean_extracted_text(S_4_4_warnings_precautions)
    
    S_4_5_interactions, remaining_text = extract_section_regex(    remaining_text,    headers.S4_5_HEADERS, headers.S4_6_HEADERS)
    S_4_5_interactions = strip_known_headers(S_4_5_interactions, headers.S4_5_HEADERS + headers.S4_6_HEADERS)
    S_4_5_interactions = clean_extracted_text(S_4_5_interactions)
    
    S_4_6_pregnancy_lactation, remaining_text = extract_section_regex(    remaining_text,    headers.S4_6_HEADERS, headers.S4_7_HEADERS)
    S_4_6_pregnancy_lactation = strip_known_headers(S_4_6_pregnancy_lactation, headers.S4_6_HEADERS + headers.S4_7_HEADERS)
    S_4_6_pregnancy_lactation = clean_extracted_text(S_4_6_pregnancy_lactation)
    
    S_4_7_driving_machines, remaining_text = extract_section_regex(    remaining_text,    headers.S4_7_HEADERS, headers.S4_8_HEADERS)
    S_4_7_driving_machines = strip_known_headers(S_4_7_driving_machines, headers.S4_7_HEADERS + headers.S4_8_HEADERS)
    S_4_7_driving_machines = clean_extracted_text(S_4_7_driving_machines)
    
     
    S_4_8_undesirable_effects, remaining_text = extract_section_regex(    remaining_text,    headers.S4_8_HEADERS, headers.S4_9_HEADERS)
    S_4_8_undesirable_effects = strip_known_headers(S_4_8_undesirable_effects, headers.S4_8_HEADERS + headers.S4_9_HEADERS)
    S_4_8_undesirable_effects = clean_extracted_text(S_4_8_undesirable_effects)
    
    S_4_9_overdose, remaining_text = extract_section_regex(    remaining_text,    headers.S4_9_HEADERS, headers.S5_1_HEADERS)
    S_4_9_overdose = strip_known_headers(S_4_9_overdose, headers.S4_9_HEADERS + headers.S5_1_HEADERS+headers.S5_HEADERS)
    S_4_9_overdose = clean_extracted_text(S_4_9_overdose)
    
    S_5_1_pharmacodynamics, remaining_text = extract_section_regex(    remaining_text,    headers.S5_1_HEADERS, headers.S5_2_HEADERS)
    S_5_1_pharmacodynamics = strip_known_headers(S_5_1_pharmacodynamics, headers.S5_1_HEADERS + headers.S5_2_HEADERS)
    S_5_1_pharmacodynamics = clean_extracted_text(S_5_1_pharmacodynamics)
    
    S_5_2_pharmacokinetics, remaining_text = extract_section_regex(    remaining_text,    headers.S5_2_HEADERS, headers.S5_3_HEADERS)
    S_5_2_pharmacokinetics = strip_known_headers(S_5_2_pharmacokinetics, headers.S5_2_HEADERS + headers.S5_3_HEADERS)
    S_5_2_pharmacokinetics = clean_extracted_text(S_5_2_pharmacokinetics)
    
    S_5_3_preclinical_data, remaining_text = extract_section_regex(    remaining_text,    headers.S5_3_HEADERS, headers.S6_1_HEADERS)
    S_5_3_preclinical_data = strip_known_headers(S_5_3_preclinical_data, headers.S5_3_HEADERS + headers.S6_1_HEADERS+headers.S6_HEADERS)
    S_5_3_preclinical_data = clean_extracted_text(S_5_3_preclinical_data)
    
    S_6_1_excipients, remaining_text = extract_section_regex(    remaining_text,    headers.S6_1_HEADERS, headers.S6_2_HEADERS)
    S_6_1_excipients = strip_known_headers(S_6_1_excipients, headers.S6_1_HEADERS + headers.S6_2_HEADERS)
    S_6_1_excipients = clean_extracted_text(S_6_1_excipients)   
    S_6_2_incompatibilities, remaining_text = extract_section_regex(    remaining_text,    headers.S6_2_HEADERS, headers.S6_3_HEADERS)
    S_6_2_incompatibilities = strip_known_headers(S_6_2_incompatibilities, headers.S6_2_HEADERS + headers.S6_3_HEADERS)
    S_6_2_incompatibilities = clean_extracted_text(S_6_2_incompatibilities)
    
    S_6_3_shelf_life, remaining_text = extract_section_regex(   remaining_text,    headers.S6_3_HEADERS, headers.S6_4_HEADERS)       
    S_6_3_shelf_life = strip_known_headers(S_6_3_shelf_life, headers.S6_3_HEADERS + headers.S6_4_HEADERS)
    S_6_3_shelf_life = clean_extracted_text(S_6_3_shelf_life)
    S_6_4_storage, remaining_text = extract_section_regex(    remaining_text,    headers.S6_4_HEADERS, headers.S6_5_HEADERS)
    #S_6_4_storage = strip_known_headers(S_6_4_storage, headers.S6_4_HEADERS + headers.S6_5_HEADERS)
    S_6_4_storage = clean_extracted_text(S_6_4_storage)
    
    S_6_5_container_description, remaining_text = extract_section_regex(    remaining_text ,    headers.S6_5_HEADERS, headers.S6_6_HEADERS)
    S_6_5_container_description = strip_known_headers(S_6_5_container_description, headers.S6_5_HEADERS + headers.S6_6_HEADERS)
    S_6_5_container_description = clean_extracted_text(S_6_5_container_description)
    
    S_6_6_handling_disposal, remaining_text = extract_section_regex(    remaining_text,    headers.S6_6_HEADERS,    headers.S7_HEADERS)
    S_6_6_handling_disposal = strip_known_headers(S_6_6_handling_disposal,  headers.S7_HEADERS)
    S_6_6_handling_disposal = clean_extracted_text(S_6_6_handling_disposal)
    
    S_7_marketing_authorisation_holder, remaining_text = extract_section_regex(    remaining_text,    headers.S7_HEADERS,    headers.S8_HEADERS)
    S_7_marketing_authorisation_holder = strip_known_headers(S_7_marketing_authorisation_holder, headers.S7_HEADERS + headers.S8_HEADERS)
    S_7_marketing_authorisation_holder = clean_extracted_text(S_7_marketing_authorisation_holder)
    
    s_8_authorisation_number, remaining_text = extract_section_regex(    remaining_text,    headers.S8_HEADERS,    r"(?:\b9\b\s*[\.\-:]?\s*)?DATE\s+OF\s+FIRST\s+AUTHORISATION(?:\s*/\s*RENEWAL\s+OF\s+THE\s+AUTHORISATION)?")
    S_8_authorisation_number = strip_known_headers(s_8_authorisation_number, headers.S8_HEADERS + headers.S9_HEADERS)
    S_8_authorisation_number = clean_extracted_text(S_8_authorisation_number)
    
    S_9_authorisation_date, remaining_text = extract_section_regex(    remaining_text,    headers.S9_HEADERS, headers.S10_HEADERS)
    S_9_authorisation_date = strip_known_headers(S_9_authorisation_date, headers.S9_HEADERS + headers.S10_HEADERS)
    S_9_authorisation_date = clean_extracted_text(S_9_authorisation_date)
    
    S_10_revision_date, remaining_text = extract_section_regex(    remaining_text,    headers.S10_HEADERS   )
    
    return {
        "country": "GB",
        "S1_Name_of_Medicinal_product": s1_text.strip(),
        "S2_composition": s2_text.strip(),
        "S3_pharmaceutical_form": s3_Pharmaceutical_form.strip(),
        "S_4_1_therapeutic_indications": S_4_1_therapeutic_indications.strip(),
        "S_4_2_posology_administration": S_4_2_posology_administration.strip(),
        "S_4_3_contraindications": S_4_3_contraindications.strip(),
        "S_4_4_warnings_precautions": S_4_4_warnings_precautions.strip(),
        "S_4_5_interactions": S_4_5_interactions.strip(),   
        "S_4_6_pregnancy_lactation": S_4_6_pregnancy_lactation.strip(),
        "S_4_7_driving_machines": S_4_7_driving_machines.strip(),
        "S_4_8_undesirable_effects": S_4_8_undesirable_effects.strip(),
        "S_4_9_overdose": S_4_9_overdose.strip(),   
        "S_5_1_pharmacodynamics": S_5_1_pharmacodynamics.strip(),
        "S_5_2_pharmacokinetics": S_5_2_pharmacokinetics.strip(),
        "S_5_3_preclinical_data": S_5_3_preclinical_data.strip(),
        "S_6_1_excipients": S_6_1_excipients.strip(),
        "S_6_2_incompatibilities": S_6_2_incompatibilities.strip(),
        "S_6_3_shelf_life": S_6_3_shelf_life.strip(),
        "S_6_4_storage": S_6_4_storage.strip(),         
        "S_6_5_container_description": S_6_5_container_description.strip(),
        "S_6_6_handling_disposal": S_6_6_handling_disposal.strip(),
        "S_7_marketing_authorisation_holder": S_7_marketing_authorisation_holder.strip(),
        "S_8_authorisation_number": clean_authotisation_text(s_8_authorisation_number.strip()),
        "S_9_authorisation_date": parse_date_safe(S_9_authorisation_date.strip()),
        "S_10_revision_date": parse_date_safe(S_10_revision_date.strip()),
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d"),
        "last_updated_by": "Bulk SPC upload Feb2026", 
        "Source_file_name": os.path.basename(pdf_path)
    }

def insert_to_sql(df: pd.DataFrame):
    print ("Inserting to SQL...")
    #df = pd.DataFrame([data])
    if "id" in df.columns:
        df.drop(columns=["id"], inplace=True)
    print ("Dropped 'id' column from DataFrame before SQL insert. Remaining columns:", df.columns.tolist())
    df.to_sql("SMPC", con=sql_conn_str, schema="staging", if_exists="append", index=False)

DEFAULT_OUT_XLSX = os.getenv("SMPC_OUT_XLSX", "extracted_smpc_data.xlsx")
DEFAULT_SHEET = "SMPC_Data"
def main():
    input_path = os.getenv("SMPC_PDF_DIR")
    if not input_path:
        print("Error: SMPC_PDF_DIR environment variable is not set.")
        print("Set it in your .env file to the folder containing SmPC PDFs.")
        sys.exit(1)

    print(f"Processing PDFs from: {input_path}")
    out_xlsx = DEFAULT_OUT_XLSX

    # pdfs = fitz.open(input_path)
    # if not pdfs:
    #     raise SystemExit(f"No PDFs found for: {input_path}")
    # with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
    #         tmp.write(pdfs.tobytes())
    #         tmp.flush()
    #         data = process_pdf(tmp.name)
    #         df = pd.DataFrame([data])
            
    #         #os.unlink(tmp.name)
    

    # with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
    #     df.to_excel(writer, index=False, sheet_name=DEFAULT_SHEET)
    # Get first 20 PDFs (sorted for repeatability)
    pdf_files = sorted(glob.glob(os.path.join(input_path, "*PLGB*.pdf")))
    if not pdf_files:
        raise SystemExit(f"No PDFs found in folder: {input_path}")

    rows = []
    for i, pdf_path in enumerate(pdf_files, start=1):
        try:
            print(f"[{i}/{len(pdf_files)}] {os.path.basename(pdf_path)}")
            data = process_pdf(pdf_path)          # ✅ pass actual file path
            rows.append(data)
        except Exception as e:
            print(f"FAIL: {pdf_path} -> {e}")
            rows.append({
                "Source_file_name": os.path.basename(pdf_path),
                "Error": str(e)
            })

    df = pd.DataFrame(rows)
    DEFAULT_OUT_JSON = os.getenv("SMPC_OUT_JSON", "extracted_smpc_data.json")
    df.to_json(DEFAULT_OUT_JSON, orient="records", lines=True, indent=2, force_ascii=False)
    insert_to_sql(df) 
    #with sql_conn_str.connect() as conn:
    #    df.to_sql("SMPC", conn, schema="staging", if_exists="append", index=False)

    #with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
    #    df.to_excel(writer, index=False, sheet_name=DEFAULT_SHEET)


    print(f"\nSaved: {out_xlsx}")
    print(f"Rows : {len(df)}")


if __name__ == "__main__":
    main()