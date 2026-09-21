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
