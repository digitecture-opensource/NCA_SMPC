from django.shortcuts import render, redirect
from django.http import Http404, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .services import load_page1_df, load_page2_details, load_smpc_list_df, load_smpc_detail, load_idmp_product_master, load_idmp_for_orphan
import logging
import urllib.request
import urllib.parse
import json
import re
from difflib import SequenceMatcher
logger = logging.getLogger("orphan.views")


def _fetch_fda_products(substance_name: str) -> list:
    """Call OpenFDA drugsatfda endpoint and return a flat list of product dicts."""
    if not substance_name:
        return []
    quoted = urllib.parse.quote(f'"{substance_name}"')
    url = f"https://api.fda.gov/drug/drugsfda.json?search=products.active_ingredients.name:{quoted}&limit=10"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.warning("FDA API call failed for %s: %s", substance_name, e)
        return []

    rows = []
    for app in data.get("results", []):
        app_number = app.get("application_number", "")
        sponsor = app.get("sponsor_name", "")
        openfda = app.get("openfda", {})

        # Build submission list with docs
        submissions = []
        for sub in app.get("submissions", []):
            docs = [
                {"url": d.get("url", ""), "type": d.get("type", ""), "date": d.get("date", "")}
                for d in sub.get("application_docs", [])
                if d.get("url")
            ]
            submissions.append({
                "type": sub.get("submission_type", ""),
                "number": sub.get("submission_number", ""),
                "status": sub.get("submission_status", ""),
                "status_date": sub.get("submission_status_date", ""),
                "class": sub.get("submission_class_code_description", ""),
                "review_priority": sub.get("review_priority", ""),
                "docs": docs,
            })

        for product in app.get("products", []):
            ingredients = ", ".join(
                i.get("name", "") for i in product.get("active_ingredients", [])
            )
            raw = {
                "application_number": app_number,
                "sponsor": sponsor,
                "openfda": openfda,
                "product": product,
                "submissions": submissions,
            }
            rows.append({
                "application_number": app_number,
                "sponsor": sponsor,
                "brand_name": product.get("brand_name", ""),
                "dosage_form": product.get("dosage_form", ""),
                "route": product.get("route", ""),
                "strength": ", ".join(
                    i.get("strength", "") for i in product.get("active_ingredients", [])
                ),
                "marketing_status": product.get("marketing_status", ""),
                "active_ingredients": ingredients,
                "pharm_class": ", ".join(openfda.get("pharm_class_epc", [])),
                "generic_name": ", ".join(openfda.get("generic_name", [])),
                "submissions": submissions,
                "raw_json": json.dumps(raw, indent=2),
            })
    return rows



def home(request):
    return render(request, "orphan/home.html")


def login_view(request):
    error = ""
    if request.method == "POST":
        user = authenticate(request,
                            username=request.POST.get("username", ""),
                            password=request.POST.get("password", ""))
        if user is not None:
            login(request, user)
            return redirect(request.GET.get("next", "/od/apply/"))
        error = "Invalid username or password."
    return render(request, "orphan/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("/login/")


def idmp_product_master(request):
    try:
        ma_df, mp_df, ap_df = load_idmp_product_master()
        ma_rows = ma_df.to_dict("records")
        mp_rows = mp_df.to_dict("records")
        ap_rows = ap_df.to_dict("records")
        ma_cols = list(ma_df.columns)
        mp_cols = list(mp_df.columns)
        ap_cols = list(ap_df.columns)
        error = None
    except Exception as e:
        logger.error("IDMP product master load failed: %s", e)
        ma_rows = mp_rows = ap_rows = []
        ma_cols = mp_cols = ap_cols = []
        error = str(e)
    return render(request, "orphan/idmp_product_master.html", {
        "ma_rows": ma_rows, "ma_cols": ma_cols,
        "mp_rows": mp_rows, "mp_cols": mp_cols,
        "ap_rows": ap_rows, "ap_cols": ap_cols,
        "error": error,
    })


@login_required
def od_apply(request):
    submitted = False
    draft_saved = False
    if request.method == "POST":
        action = request.POST.get("action", "submit")
        if action == "draft":
            draft_saved = True
        else:
            submitted = True
    return render(request, "orphan/od_apply.html", {
        "submitted": submitted,
        "draft_saved": draft_saved,
    })


def page1_list(request):
    product_q = (request.GET.get("product_q", "") or "").strip()
    substance_q = (request.GET.get("substance_q", "") or "").strip()
    status_q = (request.GET.get("status_q", "") or "").strip()
    expiry_after = (request.GET.get("expiry_after", "") or "").strip()
    expiry_before = (request.GET.get("expiry_before", "") or "").strip()

    # Multi-select OR paste list
    auth_multi = request.GET.getlist("authorisation_number")
    auth_text = request.GET.get("auth_text", "") or ""
    extra = [x.strip() for x in auth_text.replace("\n", ",").split(",") if x.strip()]
    auth_all = sorted(set([*auth_multi, *extra]))

    df = load_page1_df(
        product_q=product_q,
        substance_q=substance_q,
        flag_q=status_q,
        auth_numbers=auth_all if auth_all else None,
        expiry_after=expiry_after,
        expiry_before=expiry_before,
        top_n=2000,
    )

    rows = df.fillna("").to_dict(orient="records")

    return render(request, "orphan/page1_list.html", {
        "rows": rows,
        "product_q": product_q,
        "substance_q": substance_q,
        "status_q": status_q,
        "expiry_after": expiry_after,
        "expiry_before": expiry_before,
        "auth_text": auth_text,
        "selected_auth": auth_multi,
    })

def page2_detail(request, orphan_id: int):
    try:
        df_a, df_b = load_page2_details(orphan_id)
    except Exception as e:
        raise Http404(f"Could not load details for orphan_id={orphan_id}. Error: {e}")

    summary = df_a.fillna("").to_dict(orient="records")[0] if len(df_a) else {}
    detail = df_b.fillna("").to_dict(orient="records")[0] if len(df_b) else {}
    logger.info("Details page. Number of records in summary=%s, detail=%s", len(df_a), len(df_b))
    logger.info ("SMPC URL " + detail.get("SMPC_URL", "N/A"))
    

    sections = [
        ("OD Indication (OD)", detail.get("od_indication", "")),
        ("Full Designation Number(OD)", detail.get("designation_number_raw", "")),
        ("Orphan Condition(OD)", detail.get("orphan_condition", "")),
        ("All Indications (SMPC)", detail.get("indications", "")),
        ("All Contraindications (SMPC)", detail.get("contraindications", "")),
        ("Warnings/Precautions (SMPC)", detail.get("warnings_precautions", "")),
        ("Interactions (SMPC)", detail.get("interactions", "")),
        ("Pregnancy/Lactation (SMPC)", detail.get("pregnancy_lactation", "")),
        ("Driving/Machines (SMPC)", detail.get("driving_machines", "")),
        ("Undesirable effects (SMPC)", detail.get("undesirable_effects", "")),
        ("Overdose (SMPC)", detail.get("overdose", "")),
        ("Shelf life (SMPC)", detail.get("shelf_life", "")),
        ("Storage (SMPC)", detail.get("storage", "")),
        ("Container description (SMPC)", detail.get("container_description", "")),
        ("Handling/Disposal (SMPC)", detail.get("handling_disposal", "")),
        ("SMPC_URL ", detail.get("SMPC_URL", "")),
        
    ]

    smpc_url_toHTML = detail.get("SMPC_URL", "")

    ema_substance = summary.get("ai_ema_substance", "")
    fda_products = _fetch_fda_products(ema_substance)

    try:
        idmp_ma_df, idmp_mp_df, idmp_ap_df = load_idmp_for_orphan(orphan_id)
        idmp_ma = idmp_ma_df.fillna("").to_dict("records")
        idmp_mp = idmp_mp_df.fillna("").to_dict("records")
        idmp_ap = idmp_ap_df.fillna("").to_dict("records")
    except Exception as e:
        logger.warning("IDMP load failed for orphan %s: %s", orphan_id, e)
        idmp_ma = idmp_mp = idmp_ap = []

    return render(request, "orphan/page2_detail.html", {
        "orphan_id": orphan_id,
        "summary": summary,
        "sections": sections,
        "smpc_url_toHTML": smpc_url_toHTML,
        "fda_products": fda_products,
        "fda_substance": ema_substance,
        "idmp_ma": idmp_ma,
        "idmp_mp": idmp_mp,
        "idmp_ap": idmp_ap,
    })


def smpc_list(request):
    product_q = (request.GET.get("product_q", "") or "").strip()
    composition_q = (request.GET.get("composition_q", "") or "").strip()
    auth_date_after = (request.GET.get("auth_date_after", "") or "").strip()
    auth_date_before = (request.GET.get("auth_date_before", "") or "").strip()
    revision_date_after = (request.GET.get("revision_date_after", "") or "").strip()
    revision_date_before = (request.GET.get("revision_date_before", "") or "").strip()

    df = load_smpc_list_df(
        product_q=product_q,
        composition_q=composition_q,
        auth_date_after=auth_date_after,
        auth_date_before=auth_date_before,
        revision_date_after=revision_date_after,
        revision_date_before=revision_date_before,
    )

    rows = df.fillna("").to_dict(orient="records")

    return render(request, "orphan/smpc_list.html", {
        "rows": rows,
        "product_q": product_q,
        "composition_q": composition_q,
        "auth_date_after": auth_date_after,
        "auth_date_before": auth_date_before,
        "revision_date_after": revision_date_after,
        "revision_date_before": revision_date_before,
    })


def smpc_detail(request, smpc_id: int):
    try:
        df = load_smpc_detail(smpc_id)
    except Exception as e:
        raise Http404(f"Could not load SMPC id={smpc_id}. Error: {e}")

    if df.empty:
        raise Http404(f"No SMPC found for id={smpc_id}")

    record = df.fillna("").to_dict(orient="records")[0]

    # Summary fields shown in top card
    summary_keys = [
        "S1_Name_of_Medicinal_product",
        "S2_Composition",
        "S3_pharmaceutical_form",
        "S_7_marketing_authorisation_holder",
        "s_8_authorisation_number",
        "S_9_authorisation_date",
        "S_10_revision_date",
        "ai_ema_substance",
        "ai_ema_sms_id",
        "ai_confidence",
        "ai_rationale",
    ]
    summary = {k: record.get(k, "") for k in summary_keys}

    # All remaining columns as tabs (skip id and summary fields)
    skip = {"id"} | set(summary_keys)
    sections = [
        (col, record[col])
        for col in record
        if col not in skip and record[col] != ""
    ]

    # Fetch FDA products if EMA substance is available
    ema_substance = summary.get("ai_ema_substance", "")
    fda_products = _fetch_fda_products(ema_substance) if ema_substance else []

    return render(request, "orphan/smpc_detail.html", {
        "smpc_id": smpc_id,
        "summary": summary,
        "sections": sections,
        "fda_products": fda_products,
        "fda_substance": ema_substance,
    })


def _word_diff(text1: str, text2: str) -> list:
    """Compare two texts at word level and return list of (word, status) tuples.
    Status: 'same', 'deleted', 'added'
    Normalizes whitespace to single spaces for cleaner display.
    """
    # Normalize whitespace: collapse multiple whitespace chars (newlines, tabs, spaces) into single space
    text1 = re.sub(r'\s+', ' ', text1.strip())
    text2 = re.sub(r'\s+', ' ', text2.strip())

    # Split into words (split by spaces, but preserve space between words)
    words1 = text1.split()
    words2 = text2.split()

    matcher = SequenceMatcher(None, words1, words2)
    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for idx, word in enumerate(words1[i1:i2]):
                result.append((word, 'same'))
                if idx < len(words1[i1:i2]) - 1:
                    result.append((' ', 'same'))
        elif tag == 'delete':
            for idx, word in enumerate(words1[i1:i2]):
                result.append((word, 'deleted'))
                if idx < len(words1[i1:i2]) - 1:
                    result.append((' ', 'deleted'))
        elif tag == 'insert':
            for idx, word in enumerate(words2[j1:j2]):
                result.append((word, 'added'))
                if idx < len(words2[j1:j2]) - 1:
                    result.append((' ', 'added'))
        elif tag == 'replace':
            for idx, word in enumerate(words1[i1:i2]):
                result.append((word, 'deleted'))
                if idx < len(words1[i1:i2]) - 1:
                    result.append((' ', 'deleted'))
            for idx, word in enumerate(words2[j1:j2]):
                result.append((word, 'added'))
                if idx < len(words2[j1:j2]) - 1:
                    result.append((' ', 'added'))

    return result


def smpc_compare(request, smpc_id1: int, smpc_id2: int):
    """Compare two SMPC documents side-by-side with word-level diff highlighting."""
    try:
        df1 = load_smpc_detail(smpc_id1)
        df2 = load_smpc_detail(smpc_id2)
    except Exception as e:
        raise Http404(f"Could not load SMPCs. Error: {e}")

    if df1.empty or df2.empty:
        raise Http404("One or both SMPCs not found")

    record1 = df1.fillna("").to_dict(orient="records")[0]
    record2 = df2.fillna("").to_dict(orient="records")[0]

    # Summary fields
    summary_keys = [
        "S1_Name_of_Medicinal_product",
        "S2_Composition",
        "S3_pharmaceutical_form",
        "S_7_marketing_authorisation_holder",
        "s_8_authorisation_number",
        "S_9_authorisation_date",
        "S_10_revision_date",
    ]
    summary1 = {k: record1.get(k, "") for k in summary_keys}
    summary2 = {k: record2.get(k, "") for k in summary_keys}

    # Get all section keys (skip id and summary fields)
    skip = {"id"} | set(summary_keys)
    all_section_keys = set()
    for col in record1:
        if col not in skip and record1[col] != "":
            all_section_keys.add(col)
    for col in record2:
        if col not in skip and record2[col] != "":
            all_section_keys.add(col)

    all_section_keys = sorted(all_section_keys)

    # Compare sections
    sections = []
    for key in all_section_keys:
        text1 = record1.get(key, "")
        text2 = record2.get(key, "")
        is_identical = text1 == text2

        # Word-level diff
        if not is_identical:
            word_diff = _word_diff(text1, text2)
        else:
            word_diff = None

        sections.append({
            "name": key,
            "text1": text1,
            "text2": text2,
            "is_identical": is_identical,
            "word_diff": word_diff,  # Only populated if different
        })

    return render(request, "orphan/smpc_compare.html", {
        "smpc_id1": smpc_id1,
        "smpc_id2": smpc_id2,
        "summary1": summary1,
        "summary2": summary2,
        "sections": sections,
    })


def api_smpc_list(request):
    """API endpoint returning JSON list of all SMPCs for comparison selector."""
    try:
        df = load_smpc_list_df()
        data = df.fillna("").to_dict("records")
        return JsonResponse(data, safe=False)
    except Exception as e:
        logger.error("Failed to load SMPC list for API: %s", e)
        return JsonResponse({"error": str(e)}, status=500)