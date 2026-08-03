from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST


@login_required
@require_POST
def toggle_god_mode(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        return redirect(request.META.get("HTTP_REFERER") or "slurp_ui:inventory")
    on = request.POST.get("god_mode") == "on"
    request.session["god_mode"] = on
    return redirect(request.META.get("HTTP_REFERER") or "slurp_ui:inventory")


@login_required
@require_POST
def import_sample_xml(request: HttpRequest) -> HttpResponse:
    """Staff: import XML from data/private_sample_data/ (same as React header button)."""
    if not request.user.is_staff:
        messages.error(request, "Staff only.")
        return redirect(request.META.get("HTTP_REFERER") or "slurp_ui:inventory")
    try:
        from erp_core.sample_xml_import import import_all_private_xml

        result = import_all_private_xml()
        if isinstance(result, dict) and result.get("error"):
            messages.error(request, str(result["error"]))
        elif isinstance(result, dict) and result.get("message"):
            messages.success(request, str(result["message"]))
        elif isinstance(result, dict) and result.get("totals"):
            messages.success(request, f"Imported: {result['totals']}")
        else:
            messages.success(request, "Sample XML import finished.")
    except Exception as e:
        messages.error(request, f"Import failed: {e}")
    return redirect(request.META.get("HTTP_REFERER") or "slurp_ui:inventory")
