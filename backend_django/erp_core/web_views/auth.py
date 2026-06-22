from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.views.generic import RedirectView

from erp_core.mixins import SlurpLoginRequiredMixin


class SlurpLoginView(LoginView):
    template_name = 'erp/registration/login.html'


class SlurpLogoutView(LogoutView):
    next_page = 'login'


class HomeRedirectView(SlurpLoginRequiredMixin, RedirectView):
    pattern_name = 'inventory_dashboard'
