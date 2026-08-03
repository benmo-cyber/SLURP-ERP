from erp_core.permissions import get_user_role

from .nav import MAIN_TABS


def slurp_ui(request):
    """Inject shared chrome context for server-rendered SLURP 2.0."""
    role = get_user_role(request) or "viewer"
    god_mode = bool(request.session.get("god_mode")) and bool(
        getattr(request.user, "is_authenticated", False) and request.user.is_staff
    )
    return {
        "slurp_main_tabs": MAIN_TABS,
        "slurp_user_role": role,
        "slurp_god_mode": god_mode,
        "slurp_can_god_mode": bool(
            getattr(request.user, "is_authenticated", False) and request.user.is_staff
        ),
    }
