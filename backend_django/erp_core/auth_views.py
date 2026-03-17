"""
Auth API for ERP: login, logout, current user, CSRF, password reset.
Uses Django session auth; frontend sends credentials and CSRF token.
"""
import json
import logging
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .models import UserProfile

logger = logging.getLogger(__name__)


def _get_role(user):
    try:
        profile = getattr(user, 'erp_profile', None)
        return profile.role if profile else 'viewer'
    except Exception:
        return 'viewer'


@require_http_methods(["GET"])
@ensure_csrf_cookie
def csrf_token(request):
    """Return CSRF token for the frontend to send on POST/PUT/DELETE."""
    token = get_token(request)
    return JsonResponse({"csrfToken": token})


@require_http_methods(["POST"])
def login_view(request):
    """Authenticate and create session. Expects JSON: { username, password }."""
    try:
        data = json.loads(request.body)
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not username or not password:
        return JsonResponse({"error": "Username and password required"}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "Invalid username or password"}, status=401)
    if not user.is_active:
        return JsonResponse({"error": "Account is disabled"}, status=403)
    login(request, user)
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": "viewer"})
    return JsonResponse({
        "username": user.username,
        "email": getattr(user, "email", "") or "",
        "role": profile.role,
        "id": user.pk,
        "is_staff": bool(getattr(user, "is_staff", False)),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    })


@require_http_methods(["POST"])
def logout_view(request):
    """End session."""
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def me(request):
    """Return current user and role if authenticated."""
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    try:
        profile = request.user.erp_profile
        role = profile.role
    except Exception:
        profile = None
        role = "viewer"
        try:
            UserProfile.objects.get_or_create(user=request.user, defaults={"role": "viewer"})
            profile = request.user.erp_profile
            role = profile.role
        except Exception:
            pass
    try:
        return JsonResponse({
            "authenticated": True,
            "username": str(request.user.username),
            "email": str(getattr(request.user, "email", "") or ""),
            "role": str(role) if role is not None else "viewer",
            "id": int(request.user.pk),
            "is_staff": bool(getattr(request.user, "is_staff", False)),
            "is_superuser": bool(getattr(request.user, "is_superuser", False)),
        })
    except Exception as e:
        logger.exception("auth/me response build failed: %s", e)
        return JsonResponse({"error": "Server error", "detail": str(e)}, status=500)


@require_http_methods(["POST"])
def password_reset_request(request):
    """Request password reset email. Expects JSON: { email }."""
    try:
        data = json.loads(request.body)
        email = (data.get("email") or "").strip()
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not email:
        return JsonResponse({"error": "Email required"}, status=400)
    user = User.objects.filter(email__iexact=email).first()
    if user:
        from django.core.mail import send_mail
        from django.conf import settings
        token = default_token_generator.make_token(user)
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        frontend_url = getattr(settings, 'FRONTEND_URL', request.build_absolute_uri('/').rstrip('/'))
        reset_link = f"{frontend_url.rstrip('/')}/reset-password?uid={uid}&token={token}"
        subject = "SLURP password reset"
        message = f"Use this link to reset your password:\n\n{reset_link}\n\nIf you didn't request this, ignore this email."
        try:
            send_mail(
                subject,
                message,
                getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                [user.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.warning("Password reset email failed: %s", e)
            return JsonResponse({"error": "Could not send email. Try again later."}, status=503)
    return JsonResponse({"message": "If that email is on file, you will receive reset instructions."})


@require_http_methods(["POST"])
def password_reset_confirm_api(request, uidb64, token):
    """Set new password. Expects JSON: { new_password }."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        return JsonResponse({"error": "Invalid or expired reset link"}, status=400)
    try:
        data = json.loads(request.body)
        new_password = data.get("new_password") or ""
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if len(new_password) < 8:
        return JsonResponse({"error": "Password must be at least 8 characters"}, status=400)
    user.set_password(new_password)
    user.save()
    return JsonResponse({"message": "Password updated. You can log in now."})
