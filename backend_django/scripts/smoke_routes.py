"""Run all GET routes against live DB. Usage: python manage.py shell < scripts/smoke_routes.py"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse, get_resolver

client = Client()
user, _ = User.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True})
if not user.has_usable_password():
    user.set_password('slurp123')
    user.save()
client.force_login(user)

errors = []
ok = 0
for pattern in get_resolver().url_patterns:
    if not hasattr(pattern, 'url_patterns'):
        continue
    for p in pattern.url_patterns:
        name = getattr(p, 'name', None)
        if not name or name in ('home', 'logout'):
            continue
        try:
            kwargs = {}
            args = ()
            # Resolve URL params from DB
            if '<int:pk>' in str(p.pattern) or '<int:vendor_pk>' in str(p.pattern):
                from erp_core.models import Item, Lot, Vendor, PurchaseOrder, Customer, ProductionBatch, SalesOrder, Invoice, TemporaryException
                if 'item' in name:
                    obj = Item.objects.first()
                elif 'lot' in name:
                    obj = Lot.objects.first()
                elif 'vendor' in name or 'document' in name or 'exception_create' in name:
                    obj = Vendor.objects.first()
                elif 'po' in name:
                    obj = PurchaseOrder.objects.first()
                elif 'customer' in name and 'pricing' not in name:
                    obj = Customer.objects.first()
                elif 'batch' in name:
                    obj = ProductionBatch.objects.first()
                elif 'sales_order' in name:
                    obj = SalesOrder.objects.first()
                elif 'invoice' in name:
                    obj = Invoice.objects.first()
                elif 'exception_approve' in name:
                    obj = TemporaryException.objects.first()
                else:
                    obj = None
                if obj is None:
                    continue
                if 'vendor_pk' in str(p.pattern):
                    kwargs['vendor_pk'] = obj.pk if hasattr(obj, 'pk') else obj.id
                elif 'customer_pk' in str(p.pattern):
                    kwargs['customer_pk'] = obj.pk
                elif 'action' in str(p.pattern):
                    kwargs = {'pk': obj.pk, 'action': 'issue'}
                elif 'sub_type' in str(p.pattern):
                    kwargs = {'customer_pk': Customer.objects.first().pk if Customer.objects.exists() else 1, 'sub_type': 'contact'}
                else:
                    kwargs['pk'] = obj.pk
            url = reverse(name, args=args, kwargs=kwargs)
            r = client.get(url)
            if r.status_code >= 500:
                errors.append((name, url, r.status_code, r.content[:200]))
            elif r.status_code in (200, 302, 404):
                ok += 1
            else:
                errors.append((name, url, r.status_code, ''))
        except Exception as e:
            errors.append((name, str(e), 'EXC', ''))

print(f'OK: {ok}, ERRORS: {len(errors)}')
for e in errors:
    print(e)
