from django.apps import AppConfig


class ErpCoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'erp_core'
    verbose_name = 'ERP Core'

    def ready(self):
        import erp_core.signals  # noqa: F401
