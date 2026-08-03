from datetime import datetime



from django.contrib import messages

from django.contrib.auth.decorators import login_required

from django.db import transaction

from django.db.models import Q, Sum

from django.http import FileResponse, Http404, HttpRequest, HttpResponse

from django.shortcuts import get_object_or_404, redirect, render

from django.utils import timezone

from django.views.decorators.http import require_http_methods



from erp_core.models import (

    CriticalControlPoint,

    Formula,

    FormulaItem,

    Item,

    ItemCoaTestLine,

    Lot,

    LotCoaCertificate,

    LotCoaCustomerCopy,

    ProductionBatchInput,

    ProductionBatchOutput,

    RDFormula,

    RDFormulaLine,

    SupplierDocument,

    SupplierSurvey,

    TemporaryException,

    Vendor,

    VendorContact,

    VendorHistory,

)

from erp_core.vendor_address_display import build_display_address

from erp_core.vendor_rename import cascade_vendor_name_change



from ..nav import QUALITY_NAV



_PCT_TOLERANCE = 0.05



_VENDOR_TABS = (

    "overview",

    "contacts",

    "survey",

    "documents",

    "items",

    "exceptions",

    "history",

)



_REQUIRED_VENDOR_DOCS = [

    ("certificate_of_insurance", "Certificate of Insurance"),

    ("letter_of_guarantee", "Letter of Guarantee"),

    ("third_party_audit", "Third-Party Audit Certificate"),

    ("recall_plan", "Recall Statement"),

    ("other", "Completed Wildwood Ingredients Questionnaire"),

]



_RD_LINE_ORDER = [

    ("ingredient", 1),

    ("ingredient", 2),

    ("ingredient", 3),

    ("ingredient", 4),

    ("ingredient", 5),

    ("packaging", 1),

    ("packaging", 2),

    ("packaging", 3),

    ("labor", 1),

]





def _quality_ctx(active_tab: str, **extra):

    ctx = {

        "module": "quality",

        "sidebar_nav": QUALITY_NAV,

        "active_tab": active_tab,

        "page_css": [

            "Quality.css",

            "VendorApproval.css",

            "VendorDetail.css",

            "FinishedGoodsList.css",

            "CreateFinishedGood.css",

            "CreateVendor.css",

            "UnlinkFinishedGood.css",

            "ItemCoaTestLinesEditor.css",

            "LotTracking.css",

            "CoaLibrary.css",

            "RDFormulasList.css",

            "CriticalControlPoints.css",

        ],

    }

    ctx.update(extra)

    return ctx





def _parse_emails(text: str) -> list[str]:

    parts = []

    for chunk in (text or "").replace(";", "\n").split("\n"):

        for bit in chunk.split(","):

            bit = bit.strip()

            if bit:

                parts.append(bit)

    return parts





def _vendor_items_with_ytd(vendor: Vendor) -> list[dict]:

    current_year = datetime.now().year

    rows = []

    for item in Item.objects.filter(vendor=vendor.name).order_by("sku"):

        ytd = (

            Lot.objects.filter(item=item, received_date__year=current_year).aggregate(

                total=Sum("quantity")

            )["total"]

            or 0.0

        )

        rows.append(

            {

                "item": item,

                "ytd_usage": ytd,

            }

        )

    return rows





def _lot_trace(search: str):

    term = (search or "").strip()

    if not term:

        return None, [], []

    lot = (

        Lot.objects.select_related("item")

        .filter(Q(lot_number__iexact=term) | Q(vendor_lot_number__iexact=term))

        .first()

    )

    if not lot:

        return None, [], []



    forward = []

    for inp in (

        ProductionBatchInput.objects.select_related(

            "batch__finished_good_item", "lot"

        )

        .filter(lot=lot)

        .order_by("-batch__production_date")[:50]

    ):

        batch = inp.batch

        forward.append(

            {

                "batch_number": batch.batch_number,

                "finished_good": batch.finished_good_item.name,

                "quantity_used": inp.quantity_used,

                "date": batch.production_date,

            }

        )



    backward = []

    if lot.item.item_type == "finished_good":

        for out in (

            ProductionBatchOutput.objects.select_related("batch", "lot")

            .filter(lot=lot)

            .order_by("-batch__production_date")[:20]

        ):

            batch = out.batch

            inputs = list(

                ProductionBatchInput.objects.select_related("lot__item")

                .filter(batch=batch)

                .order_by("id")

            )

            backward.append(

                {

                    "batch_number": batch.batch_number,

                    "quantity_produced": out.quantity_produced,

                    "date": batch.production_date,

                    "inputs": inputs,

                }

            )



    return lot, forward, backward





def _rd_lines_from_formula(rd: RDFormula) -> list[dict]:

    by_key = {(l.line_type, l.sequence): l for l in rd.lines.select_related("item").all()}

    rows = []

    for lt, seq in _RD_LINE_ORDER:

        line = by_key.get((lt, seq))

        rows.append(

            {

                "line_type": lt,

                "sequence": seq,

                "row_id": f"R{seq}" if lt == "ingredient" else ("Labor" if lt == "labor" else f"P{seq}"),

                "line": line,

            }

        )

    return rows





@login_required

def quality_vendors(request: HttpRequest) -> HttpResponse:

    status = (request.GET.get("status") or "all").lower()

    vendors = Vendor.objects.all().order_by("name")

    if status == "approved":

        vendors = vendors.filter(approval_status="approved")

    elif status == "pending":

        vendors = vendors.filter(approval_status="pending")

    vendors = vendors[:300]

    rows = []

    for v in vendors:

        try:

            addr = build_display_address(v) or ""

        except Exception:

            addr = v.address or ""

        rows.append({"vendor": v, "display_address": addr})

    return render(

        request,

        "slurp_ui/quality/vendors.html",

        _quality_ctx("vendors", rows=rows, status=status, port_status="full"),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_create_vendor(request: HttpRequest) -> HttpResponse:

    if request.method == "POST":

        name = (request.POST.get("name") or "").strip()

        if not name:

            messages.error(request, "Vendor name is required.")

        elif Vendor.objects.filter(name=name).exists():

            messages.error(request, f'Vendor "{name}" already exists.')

        else:

            try:

                vendor = Vendor.objects.create(

                    name=name,

                    vendor_id=(request.POST.get("vendor_id") or "").strip() or None,

                    contact_name=(request.POST.get("contact_name") or "").strip() or None,

                    email=(request.POST.get("email") or "").strip() or None,

                    phone=(request.POST.get("phone") or "").strip() or None,

                    street_address=(request.POST.get("street_address") or "").strip() or None,

                    city=(request.POST.get("city") or "").strip() or None,

                    state=(request.POST.get("state") or "").strip() or None,

                    zip_code=(request.POST.get("zip_code") or "").strip() or None,

                    country=(request.POST.get("country") or "").strip() or "USA",

                    risk_profile=request.POST.get("risk_profile") or "2",

                    approval_status="pending",

                    notes=(request.POST.get("notes") or "").strip() or None,

                )

                messages.success(request, f"Created vendor {vendor.name}.")

                return redirect("slurp_ui:quality_vendor_detail", pk=vendor.pk)

            except Exception as e:

                messages.error(request, str(e))



    return render(

        request,

        "slurp_ui/quality/create_vendor.html",

        _quality_ctx(

            "vendors",

            risk_choices=Vendor.RISK_PROFILE_CHOICES,

            port_status="full",

        ),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_vendor_detail(request: HttpRequest, pk: int) -> HttpResponse:

    vendor = get_object_or_404(

        Vendor.objects.prefetch_related("contacts", "documents", "history", "exceptions"),

        pk=pk,

    )

    tab = (request.GET.get("tab") or "overview").lower()

    if tab not in _VENDOR_TABS:

        tab = "overview"



    if request.method == "POST":

        action = (request.POST.get("action") or "save").strip()

        redirect_tab = (request.POST.get("tab") or tab).lower()



        if action == "approve":

            vendor.approval_status = "approved"

            vendor.approved_date = timezone.now()

            vendor.approved_by = (

                (request.POST.get("approved_by") or "").strip()

                or getattr(request.user, "username", "")

                or "DOOF"

            )

            vendor.save()

            messages.success(request, f"Approved vendor {vendor.name}.")

            return redirect(f"{request.path}?tab=overview")



        if action == "save_contact":

            contact_id = (request.POST.get("contact_id") or "").strip()

            name = (request.POST.get("contact_name") or "").strip()

            if not name:

                messages.error(request, "Contact name is required.")

            else:

                payload = {

                    "name": name,

                    "title": (request.POST.get("contact_title") or "").strip() or None,

                    "emails": _parse_emails(request.POST.get("contact_emails") or ""),

                    "phone": (request.POST.get("contact_phone") or "").strip() or None,

                    "location_label": (request.POST.get("contact_location") or "").strip() or None,

                    "notes": (request.POST.get("contact_notes") or "").strip() or None,

                }

                try:

                    if contact_id:

                        contact = get_object_or_404(VendorContact, pk=int(contact_id), vendor=vendor)

                        for k, v in payload.items():

                            setattr(contact, k, v)

                        contact.save()

                        messages.success(request, "Contact updated.")

                    else:

                        VendorContact.objects.create(vendor=vendor, **payload)

                        messages.success(request, "Contact added.")

                except Exception as e:

                    messages.error(request, str(e))

            return redirect(f"{request.path}?tab=contacts")



        if action == "delete_contact":

            cid = request.POST.get("contact_id")

            try:

                VendorContact.objects.filter(pk=int(cid), vendor=vendor).delete()

                messages.success(request, "Contact deleted.")

            except Exception as e:

                messages.error(request, str(e))

            return redirect(f"{request.path}?tab=contacts")



        if action == "upload_document":

            doc_type = (request.POST.get("document_type") or "").strip()

            doc_name = (request.POST.get("document_name") or "").strip()

            upload = request.FILES.get("file")

            if not doc_type or not doc_name or not upload:

                messages.error(request, "Document type, name, and file are required.")

            else:

                try:

                    SupplierDocument.objects.create(

                        vendor=vendor,

                        document_type=doc_type,

                        document_name=doc_name,

                        file=upload.read(),

                        file_name=upload.name,

                        file_size=upload.size,

                        mime_type=upload.content_type or "application/pdf",

                        uploaded_by=getattr(request.user, "username", "") or "",

                    )

                    messages.success(request, f"Uploaded {doc_name}.")

                except Exception as e:

                    messages.error(request, str(e))

            return redirect(f"{request.path}?tab=documents")



        if action == "add_history":

            history_type = (request.POST.get("history_type") or "other").strip()

            description = (request.POST.get("description") or "").strip()

            if not description:

                messages.error(request, "Description is required.")

            else:

                VendorHistory.objects.create(

                    vendor=vendor,

                    history_type=history_type,

                    description=description,

                    created_by=getattr(request.user, "username", "") or "",

                )

                messages.success(request, "History entry added.")

            return redirect(f"{request.path}?tab=history")



        if action == "add_exception":

            material = (request.POST.get("material_commodity") or "").strip()

            intended = (request.POST.get("intended_use") or "").strip()

            justification = (request.POST.get("justification") or "").strip()

            if not material or not intended or not justification:

                messages.error(request, "Material, intended use, and justification are required.")

            else:

                TemporaryException.objects.create(

                    vendor=vendor,

                    material_commodity=material,

                    country_of_origin=(request.POST.get("country_of_origin") or "").strip() or None,

                    intended_use=intended,

                    po_number=(request.POST.get("po_number") or "").strip() or None,

                    lot_number=(request.POST.get("lot_number") or "").strip() or None,

                    justification=justification,

                    risk_summary=(request.POST.get("risk_summary") or "").strip() or None,

                    requested_by=getattr(request.user, "username", "") or "",

                )

                messages.success(request, "Exception request submitted.")

            return redirect(f"{request.path}?tab=exceptions")



        if action == "approve_exception":

            exc_id = request.POST.get("exception_id")

            try:

                exc = get_object_or_404(TemporaryException, pk=int(exc_id), vendor=vendor)

                exc.status = "approved"

                exc.approved_by = getattr(request.user, "username", "") or "DOOF"

                exc.approved_date = timezone.now()

                exc.save()

                messages.success(request, "Exception approved.")

            except Exception as e:

                messages.error(request, str(e))

            return redirect(f"{request.path}?tab=exceptions")



        if action == "approve_survey":

            survey = getattr(vendor, "survey", None)

            if survey is None:

                try:

                    survey = vendor.survey

                except SupplierSurvey.DoesNotExist:

                    survey = None

            if survey is None:

                messages.error(request, "No survey on file for this vendor.")

            else:

                survey.status = "approved"

                survey.approved_date = timezone.now()

                survey.approved_by = getattr(request.user, "username", "") or "DOOF"

                survey.save()

                messages.success(request, "Survey approved.")

            return redirect(f"{request.path}?tab=survey")



        # overview save

        old_name = vendor.name

        new_name = (request.POST.get("name") or "").strip()

        if not new_name:

            messages.error(request, "Vendor name is required.")

        else:

            vendor.name = new_name

            vendor.vendor_id = (request.POST.get("vendor_id") or "").strip() or None

            vendor.contact_name = (request.POST.get("contact_name") or "").strip() or None

            vendor.email = (request.POST.get("email") or "").strip() or None

            vendor.phone = (request.POST.get("phone") or "").strip() or None

            vendor.street_address = (request.POST.get("street_address") or "").strip() or None

            vendor.city = (request.POST.get("city") or "").strip() or None

            vendor.state = (request.POST.get("state") or "").strip() or None

            vendor.zip_code = (request.POST.get("zip_code") or "").strip() or None

            vendor.country = (request.POST.get("country") or "").strip() or "USA"

            vendor.payment_terms = (request.POST.get("payment_terms") or "").strip() or None

            vendor.notes = (request.POST.get("notes") or "").strip() or None

            vendor.approval_status = request.POST.get("approval_status") or vendor.approval_status

            vendor.risk_profile = request.POST.get("risk_profile") or vendor.risk_profile

            vendor.is_service_vendor = request.POST.get("is_service_vendor") == "on"

            vendor.service_vendor_type = (

                (request.POST.get("service_vendor_type") or "").strip() or None

            )

            try:

                vendor.save()

                if old_name != vendor.name:

                    try:

                        cascade_vendor_name_change(old_name, vendor.name)

                    except Exception as e:

                        messages.warning(request, f"Saved, but rename cascade warned: {e}")

                messages.success(request, f"Saved vendor {vendor.name}.")

                return redirect(f"{request.path}?tab={redirect_tab}")

            except Exception as e:

                messages.error(request, str(e))



    try:

        display_address = build_display_address(vendor) or ""

    except Exception:

        display_address = vendor.address or ""



    try:

        survey = vendor.survey

    except SupplierSurvey.DoesNotExist:

        survey = None



    documents = list(vendor.documents.all())

    doc_by_type = {d.document_type: d for d in documents}

    checklist = [

        {"type": t, "label": label, "doc": doc_by_type.get(t)}

        for t, label in _REQUIRED_VENDOR_DOCS

    ]



    edit_contact_id = request.GET.get("edit_contact")

    edit_contact = None

    if edit_contact_id:

        edit_contact = vendor.contacts.filter(pk=edit_contact_id).first()



    return render(

        request,

        "slurp_ui/quality/vendor_detail.html",

        _quality_ctx(

            "vendors",

            vendor=vendor,

            tab=tab,

            vendor_tabs=_VENDOR_TABS,

            display_address=display_address,

            approval_choices=Vendor.APPROVAL_STATUS_CHOICES,

            risk_choices=Vendor.RISK_PROFILE_CHOICES,

            service_type_choices=Vendor.SERVICE_VENDOR_TYPE_CHOICES,

            history_type_choices=VendorHistory.HISTORY_TYPE_CHOICES,

            document_type_choices=SupplierDocument.DOCUMENT_TYPE_CHOICES,

            survey=survey,

            documents=documents,

            doc_checklist=checklist,

            vendor_items=_vendor_items_with_ytd(vendor),

            exceptions=list(vendor.exceptions.all()[:50]),

            history_entries=list(vendor.history.all()[:50]),

            contacts=list(vendor.contacts.all()),

            edit_contact=edit_contact,

            port_status="full",

        ),

    )





@login_required

def quality_vendor_document_download(request: HttpRequest, pk: int, doc_pk: int) -> HttpResponse:

    doc = get_object_or_404(SupplierDocument, pk=doc_pk, vendor_id=pk)

    if not doc.file:

        raise Http404("Document file not found")

    response = HttpResponse(doc.file, content_type=doc.mime_type or "application/pdf")

    response["Content-Disposition"] = f'inline; filename="{doc.file_name or doc.document_name}"'

    return response





@login_required

@require_http_methods(["GET", "POST"])

def quality_lot_tracking(request: HttpRequest) -> HttpResponse:

    search = (request.GET.get("q") or request.POST.get("q") or "").strip()

    lot, forward_trace, backward_trace = _lot_trace(search)

    return render(

        request,

        "slurp_ui/quality/lot_tracking.html",

        _quality_ctx(

            "lot-tracking",

            search=search,

            lot=lot,

            forward_trace=forward_trace,

            backward_trace=backward_trace,

            port_status="full",

        ),

    )





@login_required

def quality_coa_library(request: HttpRequest) -> HttpResponse:

    tab = (request.GET.get("tab") or "customer").lower()

    if tab not in ("master", "customer"):

        tab = "customer"

    sku = (request.GET.get("sku") or "").strip()

    so = (request.GET.get("so") or "").strip()



    master_qs = LotCoaCertificate.objects.select_related("lot__item").order_by("-issued_at")

    customer_qs = LotCoaCustomerCopy.objects.select_related(

        "certificate__lot__item",

        "sales_order_lot__sales_order_item__sales_order",

    ).order_by("-created_at")



    if sku:

        master_qs = master_qs.filter(lot__item__sku=sku)

        customer_qs = customer_qs.filter(certificate__lot__item__sku=sku)

    if so:

        customer_qs = customer_qs.filter(

            sales_order_lot__sales_order_item__sales_order__so_number=so

        )



    return render(

        request,

        "slurp_ui/quality/coa_library.html",

        _quality_ctx(

            "coa-library",

            tab=tab,

            sku=sku,

            so=so,

            master_rows=list(master_qs[:200]),

            customer_rows=list(customer_qs[:200]),

            port_status="full",

        ),

    )





@login_required

def quality_coa_pdf(request: HttpRequest, pk: int) -> HttpResponse:

    cert = get_object_or_404(LotCoaCertificate, pk=pk)

    if not cert.coa_pdf:

        messages.error(request, "No PDF on file for this certificate.")

        return redirect("slurp_ui:quality_coa_library")

    return FileResponse(

        cert.coa_pdf.open("rb"),

        content_type="application/pdf",

        filename=f"coa-{cert.lot.lot_number or cert.lot_id}.pdf",

    )





@login_required

def quality_coa_customer_pdf(request: HttpRequest, pk: int) -> HttpResponse:

    copy = get_object_or_404(LotCoaCustomerCopy, pk=pk)

    if not copy.coa_pdf:

        messages.error(request, "No PDF on file for this customer COA.")

        return redirect("slurp_ui:quality_coa_library")

    ln = copy.certificate.lot.lot_number or str(copy.certificate.lot_id)

    return FileResponse(

        copy.coa_pdf.open("rb"),

        content_type="application/pdf",

        filename=f"coa-{ln}-customer.pdf",

    )





@login_required

def quality_finished_goods(request: HttpRequest) -> HttpResponse:

    items = list(

        Item.objects.filter(item_type__in=["finished_good", "distributed_item"]).order_by("sku")[

            :300

        ]

    )

    formula_fg_ids = set(

        Formula.objects.filter(finished_good_id__in=[i.id for i in items]).values_list(

            "finished_good_id", flat=True

        )

    )

    rows = [{"item": it, "has_formula": it.id in formula_fg_ids} for it in items]

    return render(

        request,

        "slurp_ui/quality/finished_goods.html",

        _quality_ctx("finished-goods", rows=rows, port_status="full"),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_create_finished_good(request: HttpRequest) -> HttpResponse:

    approved_vendors = list(

        Vendor.objects.filter(approval_status="approved").order_by("name").values_list("name", flat=True)

    )

    ingredient_items = (

        Item.objects.filter(

            item_type__in=["raw_material", "distributed_item"],

            vendor__in=approved_vendors,

        )

        .order_by("sku")[:500]

    )

    seen_sku = set()

    unique_ingredients = []

    for it in ingredient_items:

        if it.sku in seen_sku:

            continue

        seen_sku.add(it.sku)

        unique_ingredients.append(it)



    ccps = CriticalControlPoint.objects.all().order_by("name")

    rd_formulas = RDFormula.objects.order_by("-updated_at")[:100]



    if request.method == "POST":

        sku = (request.POST.get("sku") or "").strip()

        name = (request.POST.get("name") or "").strip()

        if not sku or not name:

            messages.error(request, "SKU and name are required.")

        elif Item.objects.filter(sku=sku, item_type="finished_good").exists():

            messages.error(request, f"Finished good SKU {sku} already exists.")

        else:

            try:

                line_count = int(request.POST.get("line_count") or 0)

            except ValueError:

                line_count = 0

            ingredients = []

            total_pct = 0.0

            for i in range(max(0, min(line_count, 40))):

                item_id = request.POST.get(f"ing_item_{i}")

                pct_raw = request.POST.get(f"ing_pct_{i}")

                if not item_id:

                    continue

                try:

                    pct = float(pct_raw or 0)

                except ValueError:

                    continue

                if pct <= 0:

                    continue

                ingredients.append(

                    {

                        "item_id": int(item_id),

                        "percentage": pct,

                        "notes": (request.POST.get(f"ing_notes_{i}") or "").strip() or None,

                    }

                )

                total_pct += pct



            if not ingredients:

                messages.error(request, "Add at least one formula ingredient.")

            elif abs(total_pct - 100.0) > _PCT_TOLERANCE:

                messages.error(

                    request,

                    f"Ingredient percentages must total 100% (±{_PCT_TOLERANCE}). Got {total_pct:.2f}%.",

                )

            else:

                pack_size_raw = (request.POST.get("pack_size") or "1").strip()

                try:

                    pack_size = float(pack_size_raw)

                except ValueError:

                    pack_size = 1.0

                shelf_life = None

                sl_raw = (request.POST.get("shelf_life_months") or "").strip()

                if sl_raw:

                    try:

                        shelf_life = int(sl_raw)

                    except ValueError:

                        messages.error(request, "Shelf life must be a whole number.")

                        return render(

                            request,

                            "slurp_ui/quality/create_finished_good.html",

                            _quality_ctx(

                                "finished-goods",

                                ingredient_items=unique_ingredients,

                                ccps=ccps,

                                rd_formulas=rd_formulas,

                                port_status="full",

                            ),

                        )



                ccp_id = (request.POST.get("critical_control_point") or "").strip()

                try:

                    with transaction.atomic():

                        item = Item.objects.create(

                            sku=sku,

                            name=name,

                            description=(request.POST.get("description") or "").strip() or None,

                            item_type="finished_good",

                            unit_of_measure=request.POST.get("pack_size_unit") or "lbs",

                            pack_size=pack_size,

                            on_order=0,

                        )

                        formula = Formula.objects.create(

                            finished_good=item,

                            version=(request.POST.get("formula_version") or "1.0").strip() or "1.0",

                            shelf_life_months=shelf_life,

                            critical_control_point_id=int(ccp_id) if ccp_id else None,

                            qc_parameter_name=(request.POST.get("qc_parameter_name") or "").strip()

                            or None,

                            qc_spec_min=float(request.POST.get("qc_spec_min"))

                            if (request.POST.get("qc_spec_min") or "").strip()

                            else None,

                            qc_spec_max=float(request.POST.get("qc_spec_max"))

                            if (request.POST.get("qc_spec_max") or "").strip()

                            else None,

                            notes=(request.POST.get("formula_notes") or "").strip() or None,

                        )

                        for row in ingredients:

                            FormulaItem.objects.create(

                                formula=formula,

                                item_id=row["item_id"],

                                percentage=row["percentage"],

                                notes=row["notes"],

                            )

                    messages.success(request, f"Created finished good {sku} with formula.")

                    return redirect("slurp_ui:quality_finished_good_detail", pk=item.pk)

                except Exception as e:

                    messages.error(request, str(e))



    return render(

        request,

        "slurp_ui/quality/create_finished_good.html",

        _quality_ctx(

            "finished-goods",

            ingredient_items=unique_ingredients,

            ccps=ccps,

            rd_formulas=rd_formulas,

            port_status="full",

        ),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_unlink_finished_good(request: HttpRequest) -> HttpResponse:

    finished_goods = list(Item.objects.filter(item_type="finished_good").order_by("sku"))

    formula_ids = set(Formula.objects.values_list("finished_good_id", flat=True))



    if request.method == "POST":

        item_id = request.POST.get("item_id")

        if not item_id:

            messages.error(request, "Select a finished good to unlink.")

        else:

            item = get_object_or_404(Item, pk=int(item_id), item_type="finished_good")

            try:

                sku = item.sku

                item.delete()

                messages.success(request, f"Unlinked finished good {sku}.")

                return redirect("slurp_ui:quality_finished_goods")

            except Exception as e:

                messages.error(request, str(e))



    rows = [{"item": it, "has_formula": it.id in formula_ids} for it in finished_goods]

    return render(

        request,

        "slurp_ui/quality/unlink_finished_good.html",

        _quality_ctx("finished-goods", rows=rows, port_status="full"),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_finished_good_detail(request: HttpRequest, pk: int) -> HttpResponse:

    item = get_object_or_404(Item, pk=pk)

    if item.item_type not in ("finished_good", "distributed_item"):

        messages.error(request, "Not a finished good / distributed item.")

        return redirect("slurp_ui:quality_finished_goods")



    formula = Formula.objects.filter(finished_good=item).prefetch_related("ingredients__item").first()

    if item.item_type != "finished_good":

        return render(

            request,

            "slurp_ui/quality/finished_good_detail.html",

            _quality_ctx(

                "finished-goods",

                item=item,

                formula=None,

                ingredients=[],

                can_edit_formula=False,

                port_status="full",

            ),

        )



    ingredient_items = Item.objects.filter(

        item_type__in=["raw_material", "distributed_item"]

    ).order_by("sku")[:500]

    ccps = CriticalControlPoint.objects.all().order_by("name")



    if request.method == "POST":

        if formula is None:

            formula = Formula.objects.create(finished_good=item, version="1.0")



        formula.version = (request.POST.get("version") or "1.0").strip() or "1.0"

        formula.notes = (request.POST.get("notes") or "").strip() or None

        formula.qc_parameter_name = (request.POST.get("qc_parameter_name") or "").strip() or None

        for field in (

            "qc_spec_min",

            "qc_spec_max",

            "shelf_life_months",

        ):

            raw = (request.POST.get(field) or "").strip()

            if raw == "":

                setattr(formula, field, None)

            else:

                try:

                    setattr(formula, field, float(raw) if field != "shelf_life_months" else int(raw))

                except ValueError:

                    messages.error(request, f"Invalid value for {field}.")

                    return redirect("slurp_ui:quality_finished_good_detail", pk=pk)

        for i in range(1, 7):

            setattr(

                formula,

                f"mixing_step_{i}",

                (request.POST.get(f"mixing_step_{i}") or "").strip() or None,

            )

        ccp_id = (request.POST.get("critical_control_point") or "").strip()

        formula.critical_control_point_id = int(ccp_id) if ccp_id else None



        try:

            line_count = int(request.POST.get("line_count") or 0)

        except ValueError:

            line_count = 0



        ingredients = []

        total_pct = 0.0

        for i in range(max(0, min(line_count, 40))):

            item_id = request.POST.get(f"ing_item_{i}")

            pct_raw = request.POST.get(f"ing_pct_{i}")

            if not item_id:

                continue

            try:

                pct = float(pct_raw or 0)

            except ValueError:

                continue

            if pct <= 0:

                continue

            ingredients.append(

                {

                    "item_id": int(item_id),

                    "percentage": pct,

                    "notes": (request.POST.get(f"ing_notes_{i}") or "").strip() or None,

                }

            )

            total_pct += pct



        if ingredients and abs(total_pct - 100.0) > _PCT_TOLERANCE:

            messages.error(

                request,

                f"Ingredient percentages must total 100% (±{_PCT_TOLERANCE}). Got {total_pct:.2f}%.",

            )

        else:

            try:

                with transaction.atomic():

                    formula.save()

                    FormulaItem.objects.filter(formula=formula).delete()

                    for row in ingredients:

                        FormulaItem.objects.create(

                            formula=formula,

                            item_id=row["item_id"],

                            percentage=row["percentage"],

                            notes=row["notes"],

                        )

                messages.success(request, f"Saved formula for {item.sku}.")

                return redirect("slurp_ui:quality_finished_good_detail", pk=pk)

            except Exception as e:

                messages.error(request, str(e))



        formula.refresh_from_db()



    ingredients = list(formula.ingredients.select_related("item").all()) if formula else []

    return render(

        request,

        "slurp_ui/quality/finished_good_detail.html",

        _quality_ctx(

            "finished-goods",

            item=item,

            formula=formula,

            ingredients=ingredients,

            ingredient_items=ingredient_items,

            ccps=ccps,

            can_edit_formula=True,

            port_status="full",

        ),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_item_coa_test_lines(request: HttpRequest, pk: int) -> HttpResponse:

    item = get_object_or_404(Item, pk=pk)

    if item.item_type not in ("finished_good", "distributed_item"):

        messages.error(request, "COA test lines apply only to finished goods / distributed items.")

        return redirect("slurp_ui:quality_finished_goods")



    if request.method == "POST":

        action = (request.POST.get("action") or "save").strip()

        if action == "delete":

            line_id = request.POST.get("line_id")

            try:

                ItemCoaTestLine.objects.filter(pk=int(line_id), item=item).delete()

                messages.success(request, "Test line deleted.")

            except Exception as e:

                messages.error(request, str(e))

            return redirect("slurp_ui:quality_item_coa_test_lines", pk=pk)



        line_id = (request.POST.get("line_id") or "").strip()

        test_name = (request.POST.get("test_name") or "").strip()

        spec = (request.POST.get("specification_text") or "").strip()

        if not test_name or not spec:

            messages.error(request, "Test name and specification are required.")

        else:

            try:

                sort_order = int(request.POST.get("sort_order") or 0)

            except ValueError:

                sort_order = 0

            nm_min = (request.POST.get("numeric_min") or "").strip()

            nm_max = (request.POST.get("numeric_max") or "").strip()

            payload = {

                "sort_order": sort_order,

                "test_name": test_name,

                "specification_text": spec,

                "result_kind": request.POST.get("result_kind") or "text_only",

                "numeric_min": float(nm_min) if nm_min else None,

                "numeric_max": float(nm_max) if nm_max else None,

            }

            try:

                if line_id and line_id != "new":

                    line = get_object_or_404(ItemCoaTestLine, pk=int(line_id), item=item)

                    for k, v in payload.items():

                        setattr(line, k, v)

                    line.save()

                else:

                    ItemCoaTestLine.objects.create(item=item, **payload)

                messages.success(request, "Test line saved.")

            except Exception as e:

                messages.error(request, str(e))

        return redirect("slurp_ui:quality_item_coa_test_lines", pk=pk)



    lines = list(item.coa_test_lines.all())

    return render(

        request,

        "slurp_ui/quality/item_coa_test_lines.html",

        _quality_ctx(

            "finished-goods",

            item=item,

            lines=lines,

            result_kind_choices=ItemCoaTestLine.RESULT_KIND_CHOICES,

            port_status="full",

        ),

    )





@login_required

def quality_rd_formulas(request: HttpRequest) -> HttpResponse:

    formulas = list(RDFormula.objects.prefetch_related("lines").order_by("-updated_at")[:200])

    return render(

        request,

        "slurp_ui/quality/rd_formulas.html",

        _quality_ctx("rd-formulas", formulas=formulas, port_status="full"),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_rd_formula_detail(request: HttpRequest, pk: int | None = None) -> HttpResponse:

    rd = None

    if pk is not None:

        rd = get_object_or_404(RDFormula.objects.prefetch_related("lines__item"), pk=pk)



    catalog_items = Item.objects.filter(

        item_type__in=["raw_material", "distributed_item"]

    ).order_by("sku")[:500]



    if request.method == "POST":

        action = (request.POST.get("action") or "save").strip()

        if action == "delete" and rd:

            name = rd.name

            rd.delete()

            messages.success(request, f"Deleted R&D formula {name}.")

            return redirect("slurp_ui:quality_rd_formulas")



        name = (request.POST.get("name") or "").strip()

        if not name:

            messages.error(request, "Product name is required.")

        else:

            lines_payload = []

            for idx, (lt, seq) in enumerate(_RD_LINE_ORDER):

                desc = (request.POST.get(f"desc_{idx}") or "").strip()

                item_id = (request.POST.get(f"item_{idx}") or "").strip()

                comp_raw = (request.POST.get(f"comp_{idx}") or "").strip()

                price_raw = (request.POST.get(f"price_{idx}") or "").strip()

                labor_raw = (request.POST.get(f"labor_{idx}") or "").strip()

                notes = (request.POST.get(f"notes_{idx}") or "").strip() or None

                if not desc and not item_id and not comp_raw and not price_raw and not labor_raw:

                    continue

                lines_payload.append(

                    {

                        "line_type": lt,

                        "sequence": seq,

                        "item_id": int(item_id) if item_id else None,

                        "description": desc,

                        "composition_pct": float(comp_raw) if comp_raw else None,

                        "price_per_lb": float(price_raw) if price_raw else None,

                        "labor_flat_amount": float(labor_raw) if labor_raw else None,

                        "notes": notes,

                    }

                )

            try:

                with transaction.atomic():

                    if rd is None:

                        rd = RDFormula.objects.create(

                            name=name,

                            status=request.POST.get("status") or "draft",

                            notes=(request.POST.get("notes") or "").strip() or None,

                        )

                    else:

                        rd.name = name

                        rd.status = request.POST.get("status") or rd.status

                        rd.notes = (request.POST.get("notes") or "").strip() or None

                        rd.save()

                        RDFormulaLine.objects.filter(rd_formula=rd).delete()

                    for row in lines_payload:

                        RDFormulaLine.objects.create(rd_formula=rd, **row)

                messages.success(request, f"Saved R&D formula {rd.name}.")

                return redirect("slurp_ui:quality_rd_formula_detail", pk=rd.pk)

            except Exception as e:

                messages.error(request, str(e))



    if rd:

        line_rows = _rd_lines_from_formula(rd)

        total_cost = sum((r["line"].formula_cost or 0) for r in line_rows if r.get("line"))

    else:

        line_rows = [{"line_type": lt, "sequence": seq, "row_id": f"R{seq}" if lt == "ingredient" else ("Labor" if lt == "labor" else f"P{seq}"), "line": None} for lt, seq in _RD_LINE_ORDER]

        total_cost = 0



    return render(

        request,

        "slurp_ui/quality/rd_formula_detail.html",

        _quality_ctx(

            "rd-formulas",

            rd=rd,

            line_rows=line_rows,

            catalog_items=catalog_items,

            status_choices=RDFormula.STATUS_CHOICES,

            total_cost=total_cost,

            port_status="full",

        ),

    )





@login_required

@require_http_methods(["GET", "POST"])

def quality_ccps(request: HttpRequest) -> HttpResponse:

    if request.method == "POST":

        action = (request.POST.get("action") or "create").strip()

        if action == "delete":

            ccp_id = request.POST.get("ccp_id")

            try:

                CriticalControlPoint.objects.filter(pk=int(ccp_id)).delete()

                messages.success(request, "CCP deleted.")

            except Exception as e:

                messages.error(request, str(e))

        elif action == "update":

            ccp_id = request.POST.get("ccp_id")

            name = (request.POST.get("name") or "").strip()

            try:

                order = int(request.POST.get("display_order") or 0)

            except ValueError:

                order = 0

            if not name:

                messages.error(request, "Name is required.")

            else:

                try:

                    ccp = get_object_or_404(CriticalControlPoint, pk=int(ccp_id))

                    ccp.name = name

                    ccp.display_order = order

                    ccp.save()

                    messages.success(request, "CCP updated.")

                except Exception as e:

                    messages.error(request, str(e))

        else:

            name = (request.POST.get("name") or "").strip()

            try:

                order = int(request.POST.get("display_order") or 0)

            except ValueError:

                order = 0

            if not name:

                messages.error(request, "Name is required.")

            else:

                try:

                    CriticalControlPoint.objects.create(name=name, display_order=order)

                    messages.success(request, f"Created CCP {name}.")

                except Exception as e:

                    messages.error(request, str(e))

        return redirect("slurp_ui:quality_ccps")



    ccps = CriticalControlPoint.objects.all().order_by("display_order", "name")

    return render(

        request,

        "slurp_ui/quality/ccps.html",

        _quality_ctx("ccps", ccps=ccps, port_status="full"),

    )



@login_required

@require_http_methods(["GET", "POST"])

def quality_rd_formula_create(request: HttpRequest) -> HttpResponse:

    return quality_rd_formula_detail(request, pk=None)
