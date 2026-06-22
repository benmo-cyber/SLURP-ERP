from django.contrib.auth.mixins import LoginRequiredMixin


class SlurpLoginRequiredMixin(LoginRequiredMixin):
    login_url = 'login'
