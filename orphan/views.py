from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from .services import load_page1_df, load_page2_details
from .models import ReviewItem

def in_group(user, group_name: str) -> bool:
    return user.is_authenticated and (user.groups.filter(name=group_name).exists() or user.is_superuser)

def is_submitter(user) -> bool:
    return in_group(user, "Submitters")

def is_approver(user) -> bool:
    return in_group(user, "Approvers")

@login_required
def page1_list(request):
    df = load_page1_df()

    # filter options
    product_opts = sorted(df["product_name"].dropna().unique().tolist())
    substance_opts = sorted(df["active_substance"].dropna().unique().tolist())
    auth_opts = sorted(df["authorisation_number"].dropna().astype(str).unique().tolist())

    # selected
    product = request.GET.getlist("product_name")
    substance = request.GET.getlist("active_substance")
    auth_multi = request.GET.getlist("authorisation_number")
    auth_text = request.GET.get("auth_text", "")

    extra = [x.strip() for x in auth_text.replace("\n", ",").split(",") if x.strip()]
    auth_all = set(auth_multi) | set(extra)

    if product:
        df = df[df["product_name"].isin(product)]
    if substance:
        df = df[df["active_substance"].isin(substance)]
    if auth_all:
        df = df[df["authorisation_number"].astype(str).isin(auth_all)]

    rows = df.fillna("").to_dict(orient="records")

    # attach workflow status
    ids = [r["orphan_id"] for r in rows]
    items = ReviewItem.objects.filter(orphan_id__in=ids)
    status_map = {i.orphan_id: i.status for i in items}
    for r in rows:
        r["workflow_status"] = status_map.get(r["orphan_id"], "DRAFT")

    return render(request, "orphan/page1_list.html", {
        "rows": rows,
        "product_opts": product_opts,
        "substance_opts": substance_opts,
        "auth_opts": auth_opts,
        "selected_product": product,
        "selected_substance": substance,
        "selected_auth": auth_multi,
        "auth_text": auth_text,
    })

@login_required
def page2_detail(request, orphan_id: int):
    df_a, df_b = load_page2_details(orphan_id)
    item, _ = ReviewItem.objects.get_or_create(orphan_id=orphan_id)

    summary = df_a.fillna("").to_dict(orient="records")[0] if len(df_a) else {}
    detail = df_b.fillna("").to_dict(orient="records")[0] if len(df_b) else {}

    sections = [
        ("OD Indication", detail.get("od_indication", "")),
        ("All Indications (SMPC)", detail.get("indications", "")),
        ("All Contraindications (SMPC)", detail.get("contraindications", "")),
        ("Warnings/Precautions", detail.get("warnings_precautions", "")),
        ("Interactions", detail.get("interactions", "")),
        ("Pregnancy/Lactation", detail.get("pregnancy_lactation", "")),
        ("Driving/Machines", detail.get("driving_machines", "")),
        ("Undesirable effects", detail.get("undesirable_effects", "")),
        ("Overdose", detail.get("overdose", "")),
        ("Shelf life", detail.get("shelf_life", "")),
        ("Storage", detail.get("storage", "")),
        ("Container description", detail.get("container_description", "")),
        ("Handling/Disposal", detail.get("handling_disposal", "")),
    ]

    return render(request, "orphan/page2_detail.html", {
        "orphan_id": orphan_id,
        "item": item,
        "summary": summary,
        "sections": sections,
        "can_submit": is_submitter(request.user),
        "can_approve": is_approver(request.user),
    })

@login_required
@user_passes_test(is_submitter)
def submit_item(request, orphan_id: int):
    item, _ = ReviewItem.objects.get_or_create(orphan_id=orphan_id)
    item.status = "SUBMITTED"
    item.submitted_by = request.user
    item.reviewer_comment = ""
    item.save()
    return redirect("orphan:detail", orphan_id=orphan_id)

@login_required
@user_passes_test(is_approver)
def approve_item(request, orphan_id: int):
    if request.method == "POST":
        comment = request.POST.get("comment", "").strip()
        item, _ = ReviewItem.objects.get_or_create(orphan_id=orphan_id)
        item.status = "APPROVED"
        item.reviewed_by = request.user
        item.reviewer_comment = comment
        item.save()
    return redirect("orphan:detail", orphan_id=orphan_id)

@login_required
@user_passes_test(is_approver)
def return_item(request, orphan_id: int):
    if request.method == "POST":
        comment = request.POST.get("comment", "").strip()
        item, _ = ReviewItem.objects.get_or_create(orphan_id=orphan_id)
        item.status = "RETURNED"
        item.reviewed_by = request.user
        item.reviewer_comment = comment
        item.save()
    return redirect("orphan:detail", orphan_id=orphan_id)