from django.shortcuts import render, redirect
from django.http import Http404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .services import load_page1_df, load_page2_details, load_smpc_list_df, load_smpc_detail
import logging
logger = logging.getLogger("orphan.views")



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
    return redirect("/")


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

    return render(request, "orphan/page2_detail.html", {
        "orphan_id": orphan_id,
        "summary": summary,
        "sections": sections,
        "smpc_url_toHTML": smpc_url_toHTML,
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
    ]
    summary = {k: record.get(k, "") for k in summary_keys}

    # All remaining columns as tabs (skip id and summary fields)
    skip = {"id"} | set(summary_keys)
    sections = [
        (col, record[col])
        for col in record
        if col not in skip and record[col] != ""
    ]

    return render(request, "orphan/smpc_detail.html", {
        "smpc_id": smpc_id,
        "summary": summary,
        "sections": sections,
    })