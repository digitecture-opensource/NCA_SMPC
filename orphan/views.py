from django.shortcuts import render
from django.http import Http404
from .services import load_page1_df, load_page2_details
import logging
logger = logging.getLogger("orphan.views")



def page1_list(request):
    product_q = (request.GET.get("product_q", "") or "").strip()
    substance_q = (request.GET.get("substance_q", "") or "").strip()
    status_q = (request.GET.get("status_q", "") or "").strip()

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
        top_n=2000,
    )

    rows = df.fillna("").to_dict(orient="records")

    return render(request, "orphan/page1_list.html", {
        "rows": rows,
        "product_q": product_q,
        "substance_q": substance_q,
        "status_q": status_q,
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