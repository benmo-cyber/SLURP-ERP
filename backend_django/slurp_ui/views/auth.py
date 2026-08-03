from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_http_methods

from django.conf import settings
from django.core.mail import send_mail


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("slurp_ui:inventory")
    error = ""
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "Invalid username or password"
        elif not user.is_active:
            error = "Account is disabled"
        else:
            login(request, user)
            next_url = request.GET.get("next") or reverse("slurp_ui:inventory")
            return redirect(next_url)
    return render(request, "slurp_ui/auth/login.html", {"error": error})


@require_http_methods(["POST", "GET"])
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("slurp_ui:login")


@require_http_methods(["GET", "POST"])
def forgot_password(request: HttpRequest) -> HttpResponse:
    message = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        users = list(User.objects.filter(email__iexact=email)) if email else []
        if users:
            user = users[0]
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = request.build_absolute_uri(
                reverse("slurp_ui:reset_password", kwargs={"uidb64": uid, "token": token})
            )
            send_mail(
                "SLURP password reset",
                f"Use this link to reset your password:\n\n{reset_link}\n\n"
                "If you didn't request this, ignore this email.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=True,
            )
        message = "If that email exists, a reset link was sent."
    return render(request, "slurp_ui/auth/forgot_password.html", {"message": message})


@require_http_methods(["GET", "POST"])
def reset_password(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    error = ""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(
            request,
            "slurp_ui/auth/reset_password.html",
            {"error": "Invalid or expired reset link.", "invalid": True},
        )

    if request.method == "POST":
        password = request.POST.get("new_password") or ""
        confirm = request.POST.get("confirm_password") or ""
        if len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            user.set_password(password)
            user.save()
            return redirect("slurp_ui:login")

    return render(
        request,
        "slurp_ui/auth/reset_password.html",
        {"error": error, "invalid": False},
    )
