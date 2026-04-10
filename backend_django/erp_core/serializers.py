from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers
from .models import (
    Item, ItemPackSize, Lot, CampaignLot, ProductionBatch, ProductionBatchInput, ProductionBatchOutput,
    CriticalControlPoint, Formula, FormulaItem, RDFormula, RDFormulaLine,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, Vendor, VendorContact, VendorHistory, SupplierSurvey,
    SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification, Customer, CustomerPricing, VendorPricing, SalesOrderLot, Invoice, InvoiceItem,
    ItemCoaTestLine, LotCoaCertificate, LotCoaCustomerCopy, LotCoaLineResult,
    ShipToLocation, CustomerContact, SalesCall, CustomerForecast, LotDepletionLog, LotTransactionLog, PurchaseOrderLog, ProductionLog, CheckInLog,
    LotAttributeChangeLog,
    Shipment, ShipmentItem, AccountsPayable, AccountsReceivable, Payment, BankReconciliation, FiscalPeriod, JournalEntry, JournalEntryLine, GeneralLedgerEntry,     AccountBalance
)


def validate_contact_emails_list(value):
    """Normalize and validate a list of email strings for VendorContact / CustomerContact."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError('emails must be a list of strings')
    out = []
    for e in value:
        s = (str(e) or '').strip()
        if not s:
            continue
        try:
            validate_email(s)
        except DjangoValidationError:
            raise serializers.ValidationError(f'Invalid email: {s}')
        out.append(s)
    return out


def _coerce_optional_lot_datetime(validated_data, key):
    """Normalize optional date/datetime strings on create/update to aware datetime at start of day, or None."""
    raw = validated_data.get(key)
    if raw is None:
        return
    from django.utils.dateparse import parse_datetime, parse_date
    from django.utils import timezone
    from datetime import datetime as dt_mod, time as time_mod

    if isinstance(raw, str) and not str(raw).strip():
        validated_data[key] = None
        return
    if isinstance(raw, str):
        parsed = parse_datetime(raw)
        if not parsed:
            d_only = parse_date(raw)
            if d_only:
                parsed = timezone.make_aware(dt_mod.combine(d_only, time_mod.min))
        validated_data[key] = parsed


class ItemPackSizeSerializer(serializers.ModelSerializer):
    pack_size_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ItemPackSize
        fields = '__all__'
    
    def get_pack_size_display(self, obj):
        """Return formatted pack size string"""
        return f"{obj.pack_size} {obj.pack_size_unit}"


class ItemSerializer(serializers.ModelSerializer):
    display_name_for_vendor = serializers.SerializerMethodField()
    sku_family_warnings = serializers.SerializerMethodField()

    def get_sku_family_warnings(self, obj):
        from erp_core.sku_family import item_sku_family_warnings

        return item_sku_family_warnings(obj)

    def get_display_name_for_vendor(self, obj):
        """Returns vendor_item_name if available and item has a vendor, otherwise returns name"""
        if obj.vendor_item_name and obj.vendor:
            return obj.vendor_item_name
        return obj.name
    pack_sizes = serializers.SerializerMethodField()
    default_pack_size = serializers.SerializerMethodField()
    
    class Meta:
        model = Item
        fields = '__all__'

    def validate(self, data):
        """Derive sku_parent_code / sku_pack_suffix from SKU; validate optional sku_parent_item."""
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from erp_core.sku_family import parse_sku_family

        inst = getattr(self, 'instance', None)
        item_type = data.get('item_type', getattr(inst, 'item_type', None) if inst else None)
        product_category = data.get('product_category', getattr(inst, 'product_category', None) if inst else None)
        sku = data.get('sku')
        if sku is None and inst:
            sku = inst.sku

        if item_type == 'indirect_material':
            return data

        if sku:
            parent, suffix = parse_sku_family(
                str(sku).strip(),
                product_category=product_category,
                item_type=item_type,
            )
            if parent:
                data['sku_parent_code'] = parent.upper()
                data['sku_pack_suffix'] = suffix.upper() if suffix else None

        if 'sku_parent_item' in data:
            parent_item = data['sku_parent_item']
        elif inst:
            parent_item = inst.sku_parent_item
        else:
            parent_item = None
        if parent_item is not None:
            if inst and parent_item.pk == inst.pk:
                raise DRFValidationError({'sku_parent_item': 'Item cannot be its own parent.'})
            base = (parent_item.sku_parent_code or parent_item.sku or '').strip().upper()
            pcode = (data.get('sku_parent_code') or (getattr(inst, 'sku_parent_code', None) or '')).strip().upper()
            if pcode and base and pcode != base:
                raise DRFValidationError(
                    {'sku_parent_item': 'Selected parent does not match the family code implied by this SKU.'}
                )

        return data
    
    def get_pack_sizes(self, obj):
        """Return all active pack sizes for this item"""
        active_pack_sizes = obj.pack_sizes.filter(is_active=True)
        return ItemPackSizeSerializer(active_pack_sizes, many=True).data
    
    def get_default_pack_size(self, obj):
        """Return the default pack size for this item"""
        default = obj.pack_sizes.filter(is_default=True, is_active=True).first()
        if default:
            return ItemPackSizeSerializer(default).data
        return None


class LotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)
    pack_size_obj = ItemPackSizeSerializer(read_only=True, source='pack_size')
    pack_size_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    received_date = serializers.DateTimeField(required=False, allow_null=True)
    quantity_remaining = serializers.SerializerMethodField()
    quantity_available_for_use = serializers.SerializerMethodField()
    lot_number = serializers.CharField(required=False, allow_blank=False)
    
    class Meta:
        model = Lot
        fields = '__all__'
        extra_kwargs = {
            'quantity_remaining': {'required': False},
        }
    
    def _lot_breakdown(self, obj):
        """One breakdown per lot per request (balances available vs commitments)."""
        from .lot_display_quantities import compute_lot_quantity_breakdown

        cache = self.context.setdefault("_lot_breakdown_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = compute_lot_quantity_breakdown(obj)
        return cache[obj.pk]

    def get_quantity_remaining(self, obj):
        """Physical remaining minus open sales allocations (single breakdown; balances with available)."""
        return self._lot_breakdown(obj)["quantity_remaining_after_sales"]

    def get_quantity_available_for_use(self, obj):
        """Same breakdown as committed/hold — uses normalized prod sum in arithmetic."""
        return self._lot_breakdown(obj)["quantity_available_for_use"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        b = self._lot_breakdown(instance)
        if "quantity" in data:
            data["quantity"] = b["quantity_received"]
        if "quantity_on_hold" in data:
            data["quantity_on_hold"] = b["quantity_on_hold"]
        return data

    def create(self, validated_data):
        item_id = validated_data.pop('item_id')
        item = Item.objects.get(id=item_id)
        validated_data['item'] = item
        
        # Handle received_date - convert date string to datetime if needed
        received_date = validated_data.get('received_date')
        if received_date and isinstance(received_date, str):
            from django.utils.dateparse import parse_datetime, parse_date
            from django.utils import timezone
            # Try parsing as datetime first
            parsed = parse_datetime(received_date)
            if not parsed:
                # Try parsing as date and convert to datetime
                date_obj = parse_date(received_date)
                if date_obj:
                    parsed = timezone.make_aware(timezone.datetime.combine(date_obj, timezone.datetime.min.time()))
            if parsed:
                validated_data['received_date'] = parsed
            else:
                # If parsing fails, use current time
                validated_data['received_date'] = timezone.now()
        elif not received_date:
            # If no date provided, use current time
            from django.utils import timezone
            validated_data['received_date'] = timezone.now()

        _coerce_optional_lot_datetime(validated_data, 'expiration_date')
        _coerce_optional_lot_datetime(validated_data, 'manufacture_date')

        # Set quantity_remaining based on status (remove from validated_data if present)
        validated_data.pop('quantity_remaining', None)  # Remove if present, we'll set it below
        status = validated_data.get('status', 'accepted')
        quantity = validated_data.get('quantity', 0)
        
        if status == 'accepted':
            validated_data['quantity_remaining'] = quantity
            validated_data['on_hold'] = False
        elif status == 'rejected':
            validated_data['quantity_remaining'] = 0
            validated_data['on_hold'] = False
        elif status == 'on_hold':
            validated_data['quantity_remaining'] = quantity  # Physical qty in house; not available until released
            validated_data['on_hold'] = True
            validated_data['quantity_on_hold'] = quantity  # Whole lot on hold
        else:
            validated_data['quantity_remaining'] = quantity
        
        # Ensure lot_number is set - database requires NOT NULL
        # If not provided, it should have been set in the view's create method
        # But as a safety fallback, generate one if still missing
        if not validated_data.get('lot_number'):
            # Import here to avoid circular import
            from django.db import transaction
            from django.utils import timezone
            from .models import LotNumberSequence, Lot
            
            today = timezone.now()
            year_prefix = today.strftime('%y')
            
            with transaction.atomic():
                sequence, created = LotNumberSequence.objects.select_for_update().get_or_create(
                    year_prefix=year_prefix,
                    defaults={'sequence_number': 0}
                )
                sequence.sequence_number += 1
                sequence.save()
                lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
                
                # Ensure uniqueness
                max_retries = 10
                retry_count = 0
                while Lot.objects.filter(lot_number=lot_number).exists() and retry_count < max_retries:
                    sequence.sequence_number += 1
                    sequence.save()
                    lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
                    retry_count += 1
            
            validated_data['lot_number'] = lot_number
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Sync quantity_on_hold with status; allow partial hold via quantity_on_hold."""
        if 'expiration_date' in validated_data:
            _coerce_optional_lot_datetime(validated_data, 'expiration_date')
        if 'manufacture_date' in validated_data:
            _coerce_optional_lot_datetime(validated_data, 'manufacture_date')
        validated_data.pop('quantity_remaining', None)  # SerializerMethodField; don't write
        new_qty_hold = validated_data.get('quantity_on_hold')
        new_status = validated_data.get('status', instance.status)
        qty_remaining = instance.quantity_remaining  # DB value

        if new_qty_hold is not None:
            # Partial hold: cap to 0 .. quantity_remaining and sync status
            new_qty_hold = max(0.0, min(float(new_qty_hold), qty_remaining))
            validated_data['quantity_on_hold'] = round(new_qty_hold, 2)
            if new_qty_hold >= qty_remaining:
                validated_data['status'] = 'on_hold'
                validated_data['on_hold'] = True
            elif new_qty_hold <= 0:
                validated_data['status'] = 'accepted'
                validated_data['on_hold'] = False
            else:
                validated_data['on_hold'] = True  # partial still "on hold" for display
                if new_status != 'rejected':
                    validated_data['status'] = 'on_hold'
        else:
            # Status-only update (whole lot)
            if new_status == 'on_hold':
                validated_data['on_hold'] = True
                validated_data['quantity_on_hold'] = qty_remaining
            elif new_status == 'accepted':
                validated_data['on_hold'] = False
                validated_data['quantity_on_hold'] = 0.0
            elif new_status == 'rejected':
                validated_data['on_hold'] = False
                validated_data['quantity_remaining'] = 0
                validated_data['quantity_on_hold'] = 0.0
        return super().update(instance, validated_data)


class ProductionBatchInputSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    quantity_used = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductionBatchInput
        fields = '__all__'
    
    def get_quantity_used(self, obj):
        """Preserve exact integers; ea/rolls keep extra precision; mass uses normalize_mass_quantity."""
        from .mass_quantity import normalize_mass_quantity

        qty = obj.quantity_used
        lot = obj.lot
        if getattr(lot.item, 'unit_of_measure', None) == 'ea':
            q = float(qty)
            ri = round(q)
            if abs(q - ri) <= 0.01:
                return float(ri)
            return round(q, 5)
        return normalize_mass_quantity(qty)


class ProductionBatchOutputSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = ProductionBatchOutput
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .mass_quantity import normalize_mass_quantity

        if data.get('quantity_produced') is not None:
            try:
                data['quantity_produced'] = normalize_mass_quantity(float(data['quantity_produced']))
            except (TypeError, ValueError):
                pass
        return data


class CampaignLotSerializer(serializers.ModelSerializer):
    """YYWW + product_code computed on save from anchor_date (ISO week)."""

    class Meta:
        model = CampaignLot
        fields = '__all__'
        read_only_fields = ('campaign_code', 'iso_year', 'iso_week', 'created_at', 'updated_at')

    def validate_product_code(self, value):
        v = (value or '').strip()
        if not v:
            raise serializers.ValidationError('Product code is required.')
        return v

    def create(self, validated_data):
        from django.db import IntegrityError
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                'A campaign with this code already exists for this ISO week and product code.'
            )

    def update(self, instance, validated_data):
        from django.db import IntegrityError
        try:
            return super().update(instance, validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                'A campaign with this code already exists for this ISO week and product code.'
            )


class ProductionBatchSerializer(serializers.ModelSerializer):
    finished_good_item = ItemSerializer(read_only=True)
    finished_good_item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type__in=['finished_good', 'distributed_item', 'raw_material']),
        source='finished_good_item',
        write_only=True,
        required=False
    )
    campaign = CampaignLotSerializer(read_only=True)
    campaign_id = serializers.PrimaryKeyRelatedField(
        queryset=CampaignLot.objects.all(),
        source='campaign',
        write_only=True,
        allow_null=True,
        required=False,
    )
    inputs = ProductionBatchInputSerializer(many=True, read_only=True)
    outputs = ProductionBatchOutputSerializer(many=True, read_only=True)

    class Meta:
        model = ProductionBatch
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .mass_quantity import normalize_mass_quantity

        for key in ('quantity_produced', 'quantity_actual', 'variance', 'wastes', 'spills'):
            if key in data and data[key] is not None:
                try:
                    data[key] = normalize_mass_quantity(float(data[key]))
                except (TypeError, ValueError):
                    pass
        return data

    def validate(self, data):
        data = super().validate(data)
        inst = self.instance
        if 'campaign' in data:
            campaign = data['campaign']
        elif inst:
            campaign = inst.campaign
        else:
            campaign = None
        fg = data.get('finished_good_item', inst.finished_good_item if inst else None)
        if campaign is not None and fg is not None and campaign.item_id != fg.id:
            raise serializers.ValidationError(
                {'campaign_id': 'Campaign lot must be for the same item as this batch.'}
            )

        # Closing a production batch: quantity_actual = total weight produced (inventory).
        # variance = produced − batch ticket target. wastes + spills explain shortfall when produced < target.
        merged_status = data.get('status', getattr(inst, 'status', None) if inst else None)
        merged_type = data.get('batch_type', getattr(inst, 'batch_type', None) if inst else None)
        if inst and merged_status == 'closed' and merged_type == 'production':
            from .mass_quantity import normalize_mass_quantity

            ticket = float(data.get('quantity_produced', inst.quantity_produced) or 0)
            actual_raw = data.get('quantity_actual', inst.quantity_actual)
            if actual_raw is None:
                actual_raw = inst.quantity_produced
            actual = float(actual_raw or 0)
            wastes = float(data.get('wastes', getattr(inst, 'wastes', 0) or 0) or 0)
            spills = float(data.get('spills', getattr(inst, 'spills', 0) or 0) or 0)
            data['variance'] = normalize_mass_quantity(actual - ticket)
            tol = 0.05
            if ticket - actual > tol:
                shortfall = normalize_mass_quantity(ticket - actual)
                explained = normalize_mass_quantity(wastes + spills)
                if abs(explained - shortfall) > tol:
                    raise serializers.ValidationError({
                        'non_field_errors': [
                            'When production is below the batch ticket, wastes + spills must explain the shortfall '
                            f'(target − produced = {shortfall}; wastes + spills = {explained}).'
                        ]
                    })
        return data


class FormulaItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    
    class Meta:
        model = FormulaItem
        fields = '__all__'


class CriticalControlPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriticalControlPoint
        fields = ['id', 'name', 'display_order']


class ItemCoaTestLineSerializer(serializers.ModelSerializer):
    def validate_item(self, value):
        if getattr(value, 'item_type', None) not in ('finished_good', 'distributed_item'):
            raise serializers.ValidationError('COA test lines apply only to finished good or distributed items.')
        return value

    class Meta:
        model = ItemCoaTestLine
        fields = [
            'id',
            'item',
            'sort_order',
            'test_name',
            'specification_text',
            'result_kind',
            'numeric_min',
            'numeric_max',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class LotCoaLineResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = LotCoaLineResult
        fields = ['id', 'item_line', 'test_name', 'specification_text', 'result_text', 'passes']


class LotCoaCertificateSerializer(serializers.ModelSerializer):
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    item_sku = serializers.CharField(source='lot.item.sku', read_only=True)
    item_name = serializers.CharField(source='lot.item.name', read_only=True)
    coa_pdf_url = serializers.SerializerMethodField()
    line_results = LotCoaLineResultSerializer(many=True, read_only=True)

    class Meta:
        model = LotCoaCertificate
        fields = [
            'id',
            'lot',
            'lot_number',
            'item_sku',
            'item_name',
            'quantity_snapshot',
            'customer_name',
            'customer_po',
            'qc_parameter_name_snapshot',
            'qc_spec_min_snapshot',
            'qc_spec_max_snapshot',
            'qc_result_value',
            'qc_result_pass',
            'coa_pdf',
            'coa_pdf_url',
            'issued_at',
            'updated_at',
            'recorded_by',
            'line_results',
        ]
        read_only_fields = [
            'qc_parameter_name_snapshot',
            'qc_spec_min_snapshot',
            'qc_spec_max_snapshot',
            'qc_result_value',
            'qc_result_pass',
            'coa_pdf',
            'issued_at',
            'updated_at',
            'recorded_by',
            'quantity_snapshot',
        ]

    def get_coa_pdf_url(self, obj):
        req = self.context.get('request')
        if not obj.coa_pdf:
            return None
        url = obj.coa_pdf.url
        if req:
            return req.build_absolute_uri(url)
        return url


class LotCoaCustomerCopySerializer(serializers.ModelSerializer):
    """Customer-facing COA PDF for one lot line on a sales order."""

    lot_number = serializers.CharField(source='certificate.lot.lot_number', read_only=True)
    item_sku = serializers.CharField(source='certificate.lot.item.sku', read_only=True)
    item_name = serializers.CharField(source='certificate.lot.item.name', read_only=True)
    so_number = serializers.CharField(
        source='sales_order_lot.sales_order_item.sales_order.so_number', read_only=True
    )
    coa_pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = LotCoaCustomerCopy
        fields = [
            'id',
            'certificate',
            'sales_order_lot',
            'lot_number',
            'item_sku',
            'item_name',
            'so_number',
            'customer_name',
            'customer_po',
            'quantity_snapshot',
            'coa_pdf',
            'coa_pdf_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['coa_pdf', 'created_at', 'updated_at']

    def get_coa_pdf_url(self, obj):
        req = self.context.get('request')
        if not obj.coa_pdf:
            return None
        url = obj.coa_pdf.url
        if req:
            return req.build_absolute_uri(url)
        return url


class FormulaSerializer(serializers.ModelSerializer):
    finished_good = ItemSerializer(read_only=True)
    finished_good_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type='finished_good'),
        source='finished_good',
        write_only=True
    )
    critical_control_point = CriticalControlPointSerializer(read_only=True)
    critical_control_point_id = serializers.PrimaryKeyRelatedField(
        queryset=CriticalControlPoint.objects.all(),
        source='critical_control_point',
        write_only=True,
        allow_null=True
    )
    ingredients = FormulaItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Formula
        fields = '__all__'


class RDFormulaLineSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), source='item', write_only=True, allow_null=True
    )
    formula_cost = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RDFormulaLine
        fields = '__all__'

    def get_formula_cost(self, obj):
        return obj.formula_cost


class RDFormulaSerializer(serializers.ModelSerializer):
    lines = RDFormulaLineSerializer(many=True, read_only=True)
    total_cost_per_lb = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RDFormula
        fields = '__all__'

    def get_total_cost_per_lb(self, obj):
        return obj.total_cost_per_lb


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True, required=False)
    purchase_order = serializers.PrimaryKeyRelatedField(read_only=True)
    unit_cost = serializers.FloatField(source='unit_price', read_only=False, required=False, allow_null=True)
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'purchase_order', 'item', 'item_id', 'quantity_ordered', 'quantity_received', 
                  'unit_price', 'unit_cost', 'order_uom', 'notes']


class VendorContactSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)

    class Meta:
        model = VendorContact
        fields = '__all__'

    def validate_emails(self, value):
        return validate_contact_emails_list(value)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source='vendor_customer_name', read_only=True)
    notify_party_contacts = VendorContactSerializer(many=True, read_only=True)
    notify_party_contact_ids = serializers.PrimaryKeyRelatedField(
        queryset=VendorContact.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = PurchaseOrder
        fields = '__all__'

    def validate_po_number(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError('PO number cannot be empty.')
        value = str(value).strip()
        instance = getattr(self, 'instance', None)
        if instance is not None and value != instance.po_number:
            request = self.context.get('request')
            if not request or not request.user.is_staff:
                raise serializers.ValidationError('Only staff can change the PO number.')
            if PurchaseOrder.objects.filter(po_number=value).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError('Another purchase order already uses this PO number.')
        elif instance is None:
            if PurchaseOrder.objects.filter(po_number=value).exists():
                raise serializers.ValidationError('This PO number is already in use.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        instance = getattr(self, 'instance', None)
        if instance is not None and 'order_date' in attrs:
            if instance.status != 'draft' and not (request and request.user and request.user.is_staff):
                raise serializers.ValidationError(
                    {'order_date': 'Only staff can change the PO / issue date after the order is no longer a draft.'}
                )
        if 'fulfillment_sales_order' in attrs:
            fso = attrs['fulfillment_sales_order']
        elif instance is not None:
            fso = instance.fulfillment_sales_order
        else:
            fso = None
        if fso is not None and not getattr(fso, 'drop_ship', False):
            raise serializers.ValidationError(
                {
                    'fulfillment_sales_order': (
                        'The linked sales order must be marked as drop ship. '
                        'Edit the sales order and enable Drop ship, or choose a different order.'
                    )
                }
            )
        return attrs

    def create(self, validated_data):
        ids = validated_data.pop('notify_party_contact_ids', None)
        instance = super().create(validated_data)
        if ids is not None:
            instance.notify_party_contacts.set(ids)
        return instance

    def update(self, instance, validated_data):
        ids = validated_data.pop('notify_party_contact_ids', None)
        instance = super().update(instance, validated_data)
        if ids is not None:
            instance.notify_party_contacts.set(ids)
        return instance


class SalesOrderLotSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    coa_customer_pdf_url = serializers.SerializerMethodField()
    coa_pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrderLot
        fields = [
            'id',
            'sales_order_item',
            'lot',
            'lot_id',
            'quantity_allocated',
            'created_at',
            'coa_customer_pdf_url',
            'coa_pdf_url',
        ]

    def get_coa_customer_pdf_url(self, obj):
        req = self.context.get('request')
        try:
            cc = obj.coa_customer_copy
        except LotCoaCustomerCopy.DoesNotExist:
            return None
        if not cc.coa_pdf:
            return None
        url = cc.coa_pdf.url
        if req:
            return req.build_absolute_uri(url)
        return url

    def get_coa_pdf_url(self, obj):
        """Prefer customer COA for this allocation; else master COA on the lot."""
        req = self.context.get('request')
        try:
            cc = obj.coa_customer_copy
        except LotCoaCustomerCopy.DoesNotExist:
            cc = None
        if cc and cc.coa_pdf:
            url = cc.coa_pdf.url
            return req.build_absolute_uri(url) if req else url
        try:
            cert = obj.lot.coa_certificate
            if cert and cert.coa_pdf:
                url = cert.coa_pdf.url
                return req.build_absolute_uri(url) if req else url
        except LotCoaCertificate.DoesNotExist:
            pass
        return None


class SalesOrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    allocated_lots = SalesOrderLotSerializer(many=True, read_only=True)
    
    class Meta:
        model = SalesOrderItem
        fields = '__all__'


class ShipmentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentItem
        fields = '__all__'


class ShipmentSerializer(serializers.ModelSerializer):
    items = ShipmentItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Shipment
        fields = '__all__'


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, read_only=True)
    customer_detail = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()  # Add customer field for frontend compatibility
    shipments = ShipmentSerializer(many=True, read_only=True)
    customer_po_pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrder
        fields = '__all__'

    def validate_so_number(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError('SO number cannot be empty.')
        value = str(value).strip()
        instance = getattr(self, 'instance', None)
        if instance is not None and value != instance.so_number:
            request = self.context.get('request')
            if not request or not request.user.is_staff:
                raise serializers.ValidationError('Only staff can change the SO number.')
            if SalesOrder.objects.filter(so_number=value).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError('Another sales order already uses this SO number.')
        elif instance is None:
            if SalesOrder.objects.filter(so_number=value).exists():
                raise serializers.ValidationError('This SO number is already in use.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        instance = getattr(self, 'instance', None)
        if instance is not None and 'order_date' in attrs:
            if instance.status != 'draft' and not (request and request.user and request.user.is_staff):
                raise serializers.ValidationError(
                    {'order_date': 'Only staff can change the order date after the order is no longer a draft.'}
                )
        return attrs

    def get_customer_po_pdf_url(self, obj):
        if not obj.pk or not obj.customer_po_pdf:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/api/sales-orders/{obj.pk}/customer-po/')
        return f'/api/sales-orders/{obj.pk}/customer-po/'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['customer_po_pdf_url'] = self.get_customer_po_pdf_url(instance)
        return data

    def get_customer_detail(self, obj):
        if obj.customer:
            return CustomerSerializer(obj.customer).data
        return None

    def get_customer(self, obj):
        """Get customer data including payment_terms"""
        if obj.customer:
            return CustomerSerializer(obj.customer).data
        return None


class CustomerSerializer(serializers.ModelSerializer):
    ship_to_locations_count = serializers.SerializerMethodField()
    contacts_count = serializers.SerializerMethodField()
    sales_calls_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = '__all__'
    
    def get_ship_to_locations_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_shiptolocation'")
                if cursor.fetchone() and hasattr(obj, 'ship_to_locations'):
                    return obj.ship_to_locations.filter(is_active=True).count()
        except Exception:
            pass
        return 0
    
    def get_contacts_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
                if cursor.fetchone() and hasattr(obj, 'contacts'):
                    return obj.contacts.filter(is_active=True).count()
        except Exception:
            pass
        return 0
    
    def get_sales_calls_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salescall'")
                if cursor.fetchone() and hasattr(obj, 'sales_calls'):
                    return obj.sales_calls.count()
        except Exception:
            pass
        return 0


class CustomerPricingSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.IntegerField(write_only=True, required=False)
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True, required=False)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = CustomerPricing
        fields = '__all__'
    
    def to_internal_value(self, data):
        # Make a mutable copy
        if hasattr(data, '_mutable'):
            data._mutable = True
        if not isinstance(data, dict):
            data = dict(data)
        else:
            data = data.copy()
        
        # Handle both 'customer' and 'customer_id' field names
        if 'customer' in data and 'customer_id' not in data:
            customer_val = data.get('customer')
            if customer_val is not None:
                data['customer_id'] = int(customer_val)
        
        # Handle both 'item' and 'item_id' field names  
        if 'item' in data and 'item_id' not in data:
            item_val = data.get('item')
            if item_val is not None:
                data['item_id'] = int(item_val)
        
        # Remove read_only fields before validation
        data.pop('customer', None)
        data.pop('item', None)
        
        return super().to_internal_value(data)
    
    def create(self, validated_data):
        import logging
        logger = logging.getLogger(__name__)
        
        # Get customer_id - check validated_data first, then initial_data
        customer_id = validated_data.pop('customer_id', None)
        if not customer_id and hasattr(self, 'initial_data'):
            customer_id = self.initial_data.get('customer') or self.initial_data.get('customer_id')
        
        if not customer_id:
            logger.error(f"Customer ID missing. validated_data keys: {validated_data.keys()}, initial_data: {getattr(self, 'initial_data', {})}")
            raise serializers.ValidationError({'customer': 'Customer is required'})
        
        try:
            validated_data['customer'] = Customer.objects.get(pk=int(customer_id))
        except (Customer.DoesNotExist, ValueError, TypeError) as e:
            logger.error(f"Customer lookup failed: {e}, customer_id: {customer_id}")
            raise serializers.ValidationError({'customer': f'Invalid customer ID: {customer_id}'})
        
        # Get item_id - check validated_data first, then initial_data
        item_id = validated_data.pop('item_id', None)
        if not item_id and hasattr(self, 'initial_data'):
            item_id = self.initial_data.get('item') or self.initial_data.get('item_id')
        
        if not item_id:
            logger.error(f"Item ID missing. validated_data keys: {validated_data.keys()}, initial_data: {getattr(self, 'initial_data', {})}")
            raise serializers.ValidationError({'item': 'Item is required'})
        
        try:
            validated_data['item'] = Item.objects.get(pk=int(item_id))
        except (Item.DoesNotExist, ValueError, TypeError) as e:
            logger.error(f"Item lookup failed: {e}, item_id: {item_id}")
            raise serializers.ValidationError({'item': f'Invalid item ID: {item_id}'})
        
        logger.info(f"Creating CustomerPricing with customer={validated_data.get('customer')}, item={validated_data.get('item')}, validated_data keys: {validated_data.keys()}")
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Extract and convert customer_id to customer ForeignKey
        customer_id = validated_data.pop('customer_id', None)
        if customer_id:
            try:
                validated_data['customer'] = Customer.objects.get(pk=int(customer_id))
            except (Customer.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError({'customer': f'Invalid customer ID: {customer_id}'})
        
        # Extract and convert item_id to item ForeignKey
        item_id = validated_data.pop('item_id', None)
        if item_id:
            try:
                validated_data['item'] = Item.objects.get(pk=int(item_id))
            except (Item.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError({'item': f'Invalid item ID: {item_id}'})
        
        return super().update(instance, validated_data)


class VendorPricingSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = VendorPricing
        fields = '__all__'
    
    def validate(self, data):
        # Handle both 'item' and 'item_id' field names
        item_id = data.pop('item_id', None) or self.initial_data.get('item')
        if item_id:
            try:
                data['item'] = Item.objects.get(pk=item_id)
            except Item.DoesNotExist:
                raise serializers.ValidationError({'item': 'Invalid item ID'})
        
        return data


class ShipToLocationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = ShipToLocation
        fields = '__all__'


class CustomerContactSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = CustomerContact
        fields = '__all__'

    def validate_emails(self, value):
        return validate_contact_emails_list(value)


class SalesCallSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    contact_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SalesCall
        fields = '__all__'
    
    def get_contact_name(self, obj):
        if obj.contact:
            return obj.contact.full_name
        return None


class CustomerForecastSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    
    class Meta:
        model = CustomerForecast
        fields = '__all__'


class InventoryTransactionSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = InventoryTransaction
        fields = '__all__'


class VendorHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorHistory
        fields = '__all__'


class SupplierSurveySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierSurvey
        fields = '__all__'


class SupplierDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierDocument
        fields = '__all__'


class TemporaryExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemporaryException
        fields = '__all__'


class VendorSerializer(serializers.ModelSerializer):
    history = VendorHistorySerializer(many=True, read_only=True)
    contacts = VendorContactSerializer(many=True, read_only=True)
    survey = SupplierSurveySerializer(read_only=True)
    documents = SupplierDocumentSerializer(many=True, read_only=True)
    exceptions = TemporaryExceptionSerializer(many=True, read_only=True)
    display_address = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Vendor
        # Explicit list so every scalar address field + display_address is always serialized (fields=__all__ can
        # behave inconsistently across DRF versions with extra SerializerMethodFields).
        fields = [
            'id', 'name', 'vendor_id', 'contact_name', 'email', 'phone',
            'address', 'street_address', 'city', 'state', 'zip_code', 'country',
            'approval_status', 'risk_profile', 'risk_tier', 'on_time_performance',
            'quality_complaints', 'notes', 'approved_date', 'approved_by', 'payment_terms',
            'is_service_vendor', 'service_vendor_type', 'gfsi_certified', 'gfsi_certificate_number',
            'gfsi_certification_body', 'fsma_compliant', 'ctpat_certified', 'bioterrorism_act_registered',
            'bioterrorism_number', 'risk_assessment_date', 'risk_assessment_notes', 'created_at', 'updated_at',
            'history', 'contacts', 'survey', 'documents', 'exceptions',
            'display_address',
        ]

    def get_display_address(self, obj):
        from erp_core.vendor_address_display import build_display_address

        return build_display_address(obj)


class CostMasterSerializer(serializers.ModelSerializer):
    unit_of_measure = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CostMaster
        fields = [
            'id', 'vendor_material', 'wwi_product_code', 'price_per_kg', 'price_per_lb',
            'incoterms', 'incoterms_place', 'origin', 'vendor', 'hts_code', 'tariff', 'freight_per_kg', 'cert_cost_per_kg',
            'landed_cost_per_kg', 'landed_cost_per_lb', 'margin', 'selling_price_per_kg', 'selling_price_per_lb',
            'strength', 'minimum', 'lead_time', 'notes', 'created_at', 'updated_at',
            'unit_of_measure',
        ]

    def get_unit_of_measure(self, obj):
        """Resolve Item unit (ea/lbs/kg) from wwi_product_code for display (e.g. EA for indirect materials)."""
        if not obj.wwi_product_code:
            return None
        item = Item.objects.filter(sku=obj.wwi_product_code).first()
        return getattr(item, 'unit_of_measure', None) if item else None


class CostMasterHistorySerializer(serializers.ModelSerializer):
    cost_master_detail = CostMasterSerializer(source='cost_master', read_only=True)
    
    class Meta:
        model = CostMasterHistory
        fields = '__all__'


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'


class FinishedProductSpecificationSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type='finished_good'),
        source='item',
        write_only=True,
        required=False
    )
    fps_pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = FinishedProductSpecification
        fields = '__all__'
    
    def get_fps_pdf_url(self, obj):
        if obj.fps_pdf:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.fps_pdf.url)
            return obj.fps_pdf.url
        return None


class InvoiceItemSerializer(serializers.ModelSerializer):
    sales_order_item = SalesOrderItemSerializer(read_only=True)
    
    class Meta:
        model = InvoiceItem
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    sales_order = serializers.SerializerMethodField()
    days_aging = serializers.SerializerMethodField()  # Changed to SerializerMethodField to handle manually created objects
    # Map database field names to expected frontend field names
    tax = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()
    freight = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    # Add customer_name and payment_terms from invoice or sales order
    customer_name = serializers.SerializerMethodField()
    payment_terms = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = '__all__'

    def validate_invoice_number(self, value):
        if value is None or (isinstance(value, str) and not str(value).strip()):
            raise serializers.ValidationError('Invoice number cannot be empty.')
        value = str(value).strip()
        instance = getattr(self, 'instance', None)
        if instance is not None and value != instance.invoice_number:
            request = self.context.get('request')
            if not request or not request.user.is_staff:
                raise serializers.ValidationError('Only staff can change the invoice number.')
            if Invoice.objects.filter(invoice_number=value).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError('Another invoice already uses this number.')
        elif instance is None:
            if Invoice.objects.filter(invoice_number=value).exists():
                raise serializers.ValidationError('This invoice number is already in use.')
        return value
    
    def get_days_aging(self, obj):
        """Calculate days aging - only count after invoice is Issued (sent)."""
        try:
            if hasattr(obj, 'days_aging'):
                return obj.days_aging
            from django.utils import timezone
            if obj.status == 'paid':
                return 0
            if obj.status == 'draft':
                return 0  # Don't start aging until Issued
            if not hasattr(obj, 'due_date') or not obj.due_date:
                return 0
            today = timezone.now().date()
            return (today - obj.due_date).days
        except Exception:
            return 0
    
    def get_customer_name(self, obj):
        """Get customer name from invoice or sales order"""
        # First try to get from invoice's customer_vendor_name field
        if hasattr(obj, 'customer_vendor_name') and obj.customer_vendor_name:
            return obj.customer_vendor_name
        # Fall back to sales order
        if hasattr(obj, 'sales_order') and obj.sales_order:
            if hasattr(obj.sales_order, 'customer_name') and obj.sales_order.customer_name:
                return obj.sales_order.customer_name
            if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer:
                return obj.sales_order.customer.name
        return None
    
    def get_payment_terms(self, obj):
        """Get payment terms from sales order customer"""
        if hasattr(obj, 'sales_order') and obj.sales_order:
            if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer:
                return getattr(obj.sales_order.customer, 'payment_terms', None)
        return None
    
    def get_tax(self, obj):
        """Map tax_amount to tax for frontend compatibility"""
        return getattr(obj, 'tax_amount', getattr(obj, 'tax', 0.0))
    
    def get_grand_total(self, obj):
        """Map total_amount to grand_total for frontend compatibility"""
        return getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0.0))
    
    def get_freight(self, obj):
        """Get freight - may not exist in database"""
        return getattr(obj, 'freight', 0.0)
    
    def get_discount(self, obj):
        """Get discount - may not exist in database"""
        return getattr(obj, 'discount', 0.0)
    
    def get_sales_order(self, obj):
        """Get sales order - handle case where sales_order_id column doesn't exist"""
        from .models import SalesOrder
        try:
            # Strategy 1: If sales_order is already attached to the object, use it (but ensure customer is loaded)
            if hasattr(obj, 'sales_order') and obj.sales_order is not None:
                # Check if customer is loaded
                if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer is not None:
                    # Customer is loaded, serialize it
                    return SalesOrderSerializer(obj.sales_order).data
                else:
                    # Customer not loaded, reload with customer
                    try:
                        so = SalesOrder.objects.select_related('customer').get(id=obj.sales_order.id)
                        return SalesOrderSerializer(so).data
                    except SalesOrder.DoesNotExist:
                        # Sales order was deleted, return None
                        return None
            
            # Strategy 2: Get sales_order_id from any source and load it
            sales_order_id = None
            if hasattr(obj, 'sales_order_id') and obj.sales_order_id:
                sales_order_id = obj.sales_order_id
            elif hasattr(obj, '_sales_order_id') and obj._sales_order_id:
                sales_order_id = obj._sales_order_id
            
            if sales_order_id:
                try:
                    so = SalesOrder.objects.select_related('customer').get(id=sales_order_id)
                    return SalesOrderSerializer(so).data
                except SalesOrder.DoesNotExist:
                    # Sales order doesn't exist
                    return None
            
            # Strategy 3: Try to find from notes (fallback for old invoices)
            if hasattr(obj, 'notes') and obj.notes:
                import re
                # Look for "sales order {so_number}" or "from sales order {id}"
                match = re.search(r'sales order[:\s]+([A-Z0-9-]+)', obj.notes, re.IGNORECASE)
                if match:
                    so_identifier = match.group(1)
                    try:
                        # Try as SO number first
                        so = SalesOrder.objects.select_related('customer').get(so_number=so_identifier)
                        return SalesOrderSerializer(so).data
                    except SalesOrder.DoesNotExist:
                        try:
                            # Try as ID
                            so = SalesOrder.objects.select_related('customer').get(id=int(so_identifier))
                            return SalesOrderSerializer(so).data
                        except (ValueError, SalesOrder.DoesNotExist):
                            pass
            
            return None
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting sales order for invoice {getattr(obj, 'invoice_number', 'unknown')}: {e}")
            logger.error(traceback.format_exc())
            return None


class LotTransactionLogSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    
    class Meta:
        model = LotTransactionLog
        fields = '__all__'


class LotDepletionLogSerializer(serializers.ModelSerializer):
    lot_number_display = serializers.CharField(source='lot_number', read_only=True)
    item_sku_display = serializers.CharField(source='item_sku', read_only=True)
    item_name_display = serializers.CharField(source='item_name', read_only=True)
    depletion_method_display = serializers.CharField(source='get_depletion_method_display', read_only=True)
    
    class Meta:
        model = LotDepletionLog
        fields = '__all__'
        read_only_fields = ['depleted_at']


class PurchaseOrderLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    po_number_display = serializers.CharField(source='po_number', read_only=True)
    
    class Meta:
        model = PurchaseOrderLog
        fields = '__all__'
        read_only_fields = ['logged_at']


class FiscalPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalPeriod
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class JournalEntryLineSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = JournalEntryLine
        fields = '__all__'


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalEntryLineSerializer(many=True, read_only=True)
    total_debits = serializers.SerializerMethodField()
    total_credits = serializers.SerializerMethodField()
    is_balanced = serializers.SerializerMethodField()
    
    class Meta:
        model = JournalEntry
        fields = '__all__'
        read_only_fields = ['entry_number', 'created_at', 'updated_at', 'posted_at']
    
    def get_total_debits(self, obj):
        return sum(line.amount for line in obj.lines.filter(debit_credit='debit'))
    
    def get_total_credits(self, obj):
        return sum(line.amount for line in obj.lines.filter(debit_credit='credit'))
    
    def get_is_balanced(self, obj):
        return abs(self.get_total_debits(obj) - self.get_total_credits(obj)) < 0.01


class GeneralLedgerEntrySerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    journal_entry_number = serializers.CharField(source='journal_entry.entry_number', read_only=True)
    
    class Meta:
        model = GeneralLedgerEntry
        fields = '__all__'
        read_only_fields = ['created_at']


class AccountBalanceSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    period_name = serializers.CharField(source='fiscal_period.period_name', read_only=True)
    
    class Meta:
        model = AccountBalance
        fields = '__all__'
        read_only_fields = ['last_updated']


class AccountsPayableSerializer(serializers.ModelSerializer):
    days_aging = serializers.ReadOnlyField()
    aging_bucket = serializers.ReadOnlyField()
    vendor_display = serializers.SerializerMethodField()
    po_number = serializers.SerializerMethodField()
    
    class Meta:
        model = AccountsPayable
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'balance', 'status', 'days_aging', 'aging_bucket']
    
    def get_vendor_display(self, obj):
        return obj.vendor_name
    
    def get_po_number(self, obj):
        po = getattr(obj, 'purchase_order', None)
        if po is not None:
            return po.po_number
        return None


class AccountsReceivableSerializer(serializers.ModelSerializer):
    days_aging = serializers.ReadOnlyField()
    aging_bucket = serializers.ReadOnlyField()
    customer_display = serializers.SerializerMethodField()
    invoice_number_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AccountsReceivable
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'balance', 'status', 'days_aging', 'aging_bucket']
    
    def get_customer_display(self, obj):
        return obj.customer_name
    
    def get_invoice_number_display(self, obj):
        try:
            return obj.invoice.invoice_number if obj.invoice else None
        except Exception:
            # If invoice is not loaded, try to get it from the invoice_id
            if hasattr(obj, 'invoice_id') and obj.invoice_id:
                from .models import Invoice
                try:
                    invoice = Invoice.objects.get(id=obj.invoice_id)
                    return invoice.invoice_number
                except Invoice.DoesNotExist:
                    return None
            return None


class PaymentSerializer(serializers.ModelSerializer):
    ap_entry_display = serializers.SerializerMethodField()
    ar_entry_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_ap_entry_display(self, obj):
        if obj.ap_entry:
            return f"{obj.ap_entry.vendor_name} - ${obj.ap_entry.balance}"
        return None
    
    def get_ar_entry_display(self, obj):
        if obj.ar_entry:
            return f"{obj.ar_entry.customer_name} - ${obj.ar_entry.balance}"
        return None


class BankReconciliationSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = BankReconciliation
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ProductionLogSerializer(serializers.ModelSerializer):
    batch_number_display = serializers.CharField(source='batch_number', read_only=True)
    finished_good_sku_display = serializers.CharField(source='finished_good_sku', read_only=True)
    
    class Meta:
        model = ProductionLog
        fields = '__all__'
        read_only_fields = ['logged_at']


class CheckInLogSerializer(serializers.ModelSerializer):
    item_display = serializers.SerializerMethodField()
    lot_number_display = serializers.CharField(source='lot_number', read_only=True)
    
    class Meta:
        model = CheckInLog
        fields = '__all__'
        read_only_fields = ['checked_in_at']
    
    def get_item_display(self, obj):
        return f"{obj.item_sku} - {obj.item_name}"


class LotAttributeChangeLogSerializer(serializers.ModelSerializer):
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    item_sku = serializers.CharField(source='lot.item.sku', read_only=True)

    class Meta:
        model = LotAttributeChangeLog
        fields = '__all__'
        read_only_fields = ['changed_at']

