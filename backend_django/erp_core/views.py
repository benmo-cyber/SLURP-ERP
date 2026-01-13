from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import models
from datetime import datetime
from .models import (
    Item, Lot, ProductionBatch, ProductionBatchInput, ProductionBatchOutput, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, LotNumberSequence, Vendor, VendorHistory,
    SupplierSurvey, SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification, Customer, CustomerPricing, VendorPricing, SalesOrderLot, Invoice, InvoiceItem,
    ShipToLocation, CustomerContact, SalesCall, CustomerForecast, BatchNumberSequence
)
from .serializers import (
    ItemSerializer, LotSerializer, ProductionBatchSerializer,
    FormulaSerializer, FormulaItemSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    SalesOrderSerializer, SalesOrderItemSerializer,
    InventoryTransactionSerializer, VendorSerializer, VendorHistorySerializer,
    SupplierSurveySerializer, SupplierDocumentSerializer, TemporaryExceptionSerializer,
    CostMasterSerializer, CostMasterHistorySerializer, AccountSerializer,
    FinishedProductSpecificationSerializer, CustomerSerializer, CustomerPricingSerializer, VendorPricingSerializer,
    InvoiceSerializer, InvoiceItemSerializer, ShipToLocationSerializer,
    CustomerContactSerializer, SalesCallSerializer, CustomerForecastSerializer
)


def generate_lot_number():
    """Generate a unique lot number in format 1yy00000 (7 digits: 1 + year + 5-digit sequence)"""
    from django.db import transaction
    from .models import LotNumberSequence
    
    today = timezone.now()
    year_prefix = today.strftime('%y')  # 2-digit year
    
    # Use select_for_update to lock the row and prevent race conditions
    with transaction.atomic():
        # Get or create sequence for this year with lock
        sequence, created = LotNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix,
            defaults={'sequence_number': 0}
        )
        
        # Increment sequence
        sequence.sequence_number += 1
        sequence.save()
        
        # Format: 1 + yy + 5-digit sequence (1yy00000)
        lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
        
        # Double-check uniqueness (in case of any edge case)
        max_retries = 10
        retry_count = 0
        while Lot.objects.filter(lot_number=lot_number).exists() and retry_count < max_retries:
            sequence.sequence_number += 1
            sequence.save()
            lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
            retry_count += 1
        
        if retry_count >= max_retries:
            # Fallback: add timestamp milliseconds for uniqueness
            import time
            lot_number = f"1{year_prefix}{sequence.sequence_number:05d}{int(time.time() * 1000) % 1000:03d}"
    
    return lot_number

def generate_po_number():
    """Generate a unique PO number in format 2yy0000 (7 digits: 2 + year + 4-digit sequence)"""
    from django.db import transaction
    from .models import PONumberSequence
    
    today = timezone.now()
    year_prefix = today.strftime('%y')  # 2-digit year
    
    with transaction.atomic():
        sequence, created = PONumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix,
            defaults={'sequence_number': 0}
        )
        
        sequence.sequence_number += 1
        sequence.save()
        
        # Format: 2 + yy + 4-digit sequence (2yy0000)
        po_number = f"2{year_prefix}{sequence.sequence_number:04d}"
        
        # Double-check uniqueness
        max_retries = 10
        retry_count = 0
        from .models import PurchaseOrder
        while PurchaseOrder.objects.filter(po_number=po_number).exists() and retry_count < max_retries:
            sequence.sequence_number += 1
            sequence.save()
            po_number = f"2{year_prefix}{sequence.sequence_number:04d}"
            retry_count += 1
    
    return po_number

def generate_sales_order_number():
    """Generate a unique sales order number in format 3yy0000 (7 digits: 3 + year + 4-digit sequence)"""
    from django.db import transaction
    from .models import SalesOrderNumberSequence
    
    today = timezone.now()
    year_prefix = today.strftime('%y')  # 2-digit year
    
    with transaction.atomic():
        sequence, created = SalesOrderNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix,
            defaults={'sequence_number': 0}
        )
        
        sequence.sequence_number += 1
        sequence.save()
        
        # Format: 3 + yy + 4-digit sequence (3yy0000)
        so_number = f"3{year_prefix}{sequence.sequence_number:04d}"
        
        # Double-check uniqueness
        max_retries = 10
        retry_count = 0
        from .models import SalesOrder
        while SalesOrder.objects.filter(so_number=so_number).exists() and retry_count < max_retries:
            sequence.sequence_number += 1
            sequence.save()
            so_number = f"3{year_prefix}{sequence.sequence_number:04d}"
            retry_count += 1
    
    return so_number

def generate_customer_id():
    """Generate a unique customer ID in format 001, 002, etc. (3-digit sequence)"""
    from django.db import transaction
    from django.db.utils import OperationalError
    from .models import Customer, CustomerNumberSequence
    
    try:
        # Try to use the sequence table if it exists
        with transaction.atomic():
            # Get or create the single sequence record with lock
            sequence, created = CustomerNumberSequence.objects.select_for_update().get_or_create(
                id=1,  # Single sequence record
                defaults={'sequence_number': 0}
            )
            
            sequence.sequence_number += 1
            sequence.save()
            
            # Format: 3-digit sequence (001, 002, etc.)
            customer_id = f"{sequence.sequence_number:03d}"
            
            # Double-check uniqueness
            max_retries = 10
            retry_count = 0
            while Customer.objects.filter(customer_id=customer_id).exists() and retry_count < max_retries:
                sequence.sequence_number += 1
                sequence.save()
                customer_id = f"{sequence.sequence_number:03d}"
                retry_count += 1
            
            return customer_id
    except (OperationalError, Exception) as e:
        # If sequence table doesn't exist yet, fall back to finding max customer_id
        # This handles the case where migrations haven't been run yet
        try:
            # Get all existing customer IDs and find the highest numeric one
            existing_customers = Customer.objects.exclude(customer_id__isnull=True).exclude(customer_id='')
            max_id = 0
            
            for customer in existing_customers:
                try:
                    # Try to parse customer_id as integer
                    customer_num = int(customer.customer_id)
                    if customer_num > max_id:
                        max_id = customer_num
                except (ValueError, TypeError):
                    # If customer_id is not numeric, skip it
                    continue
            
            # Generate next ID
            next_id = max_id + 1
            customer_id = f"{next_id:03d}"
            
            # Double-check uniqueness
            max_retries = 10
            retry_count = 0
            while Customer.objects.filter(customer_id=customer_id).exists() and retry_count < max_retries:
                next_id += 1
                customer_id = f"{next_id:03d}"
                retry_count += 1
            
            return customer_id
        except Exception:
            # Ultimate fallback: start from 001
            return "001"

def generate_invoice_number():
    """Generate a unique invoice number in format 4yy0000 (7 digits: 4 + year + 4-digit sequence)"""
    from django.db import transaction
    from .models import InvoiceNumberSequence
    
    today = timezone.now()
    year_prefix = today.strftime('%y')  # 2-digit year
    
    with transaction.atomic():
        sequence, created = InvoiceNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix,
            defaults={'sequence_number': 0}
        )
        
        sequence.sequence_number += 1
        sequence.save()
        
        # Format: 4 + yy + 4-digit sequence (4yy0000)
        invoice_number = f"4{year_prefix}{sequence.sequence_number:04d}"
        
        # Double-check uniqueness (if Invoice model exists)
        try:
            from .models import Invoice
            max_retries = 10
            retry_count = 0
            while Invoice.objects.filter(invoice_number=invoice_number).exists() and retry_count < max_retries:
                sequence.sequence_number += 1
                sequence.save()
                invoice_number = f"4{year_prefix}{sequence.sequence_number:04d}"
                retry_count += 1
        except ImportError:
            # Invoice model doesn't exist yet, that's okay
            pass
    
    return invoice_number

def generate_batch_number(batch_type='production'):
    """Generate a unique batch number in format BATCH-YYYYMMDD-001 or REPACK-YYYYMMDD-001"""
    from django.db import transaction
    from .models import BatchNumberSequence
    
    today = timezone.now()
    date_prefix = today.strftime('%Y%m%d')  # YYYYMMDD
    prefix = 'REPACK' if batch_type == 'repack' else 'BATCH'
    
    # Use select_for_update to lock the row and prevent race conditions
    with transaction.atomic():
        # Get or create sequence for this date with lock
        sequence, created = BatchNumberSequence.objects.select_for_update().get_or_create(
            date_prefix=date_prefix,
            defaults={'sequence_number': 0}
        )
        
        # Increment sequence
        sequence.sequence_number += 1
        sequence.save()
        
        # Format: PREFIX-YYYYMMDD-001
        batch_number = f"{prefix}-{date_prefix}-{sequence.sequence_number:03d}"
        
        # Double-check uniqueness (in case of any edge case)
        max_retries = 10
        retry_count = 0
        while ProductionBatch.objects.filter(batch_number=batch_number).exists() and retry_count < max_retries:
            sequence.sequence_number += 1
            sequence.save()
            batch_number = f"{prefix}-{date_prefix}-{sequence.sequence_number:03d}"
            retry_count += 1
        
        if retry_count >= max_retries:
            # Fallback: add timestamp milliseconds for uniqueness
            import time
            batch_number = f"{prefix}-{date_prefix}-{sequence.sequence_number:03d}-{int(time.time() * 1000) % 1000:03d}"
    
    return batch_number


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    
    def get_queryset(self):
        queryset = Item.objects.all()
        # Filter by approved vendors if requested
        approved_only = self.request.query_params.get('approved_vendors_only', None)
        if approved_only == 'true':
            approved_vendor_names = Vendor.objects.filter(approval_status='approved').values_list('name', flat=True)
            queryset = queryset.filter(vendor__in=approved_vendor_names)
        return queryset
    
    def create(self, request, *args, **kwargs):
        # Clean up the data - convert empty strings to None for optional fields
        data = request.data.copy()
        if 'description' in data and data['description'] == '':
            data['description'] = None
        if 'vendor' in data and data['vendor'] == '':
            data['vendor'] = None
        if 'pack_size' in data and (data['pack_size'] == '' or data['pack_size'] is None):
            data.pop('pack_size', None)
        if 'price' in data and (data['price'] == '' or data['price'] is None):
            data.pop('price', None)
        
        # Ensure on_order is set to 0 if not provided
        if 'on_order' not in data:
            data['on_order'] = 0
        
        # Check for duplicate SKU + vendor combination
        if data.get('sku') and data.get('vendor'):
            existing = Item.objects.filter(sku=data['sku'], vendor=data['vendor']).first()
            if existing:
                return Response(
                    {'error': f'Item with SKU "{data["sku"]}" already exists for vendor "{data["vendor"]}". Each vendor can only have one item per SKU.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        
        # Auto-create CostMaster entry when item is created
        if item.vendor:
            # Convert price based on unit of measure
            price_per_kg = None
            price_per_lb = None
            freight_per_kg = 0.0
            
            if data.get('price'):
                price = float(data['price'])
                unit_of_measure = data.get('unit_of_measure', 'lbs')
                
                if unit_of_measure == 'lbs':
                    price_per_lb = price
                    price_per_kg = price * 2.20462  # Convert lb to kg
                elif unit_of_measure == 'kg':
                    price_per_kg = price
                    price_per_lb = price / 2.20462  # Convert kg to lb
                else:
                    # For 'ea', use price as-is for both (or handle differently)
                    price_per_kg = price
                    price_per_lb = price
            
            # Calculate landed cost (price + freight)
            landed_cost_per_kg = None
            landed_cost_per_lb = None
            if price_per_kg is not None:
                landed_cost_per_kg = price_per_kg + freight_per_kg
            if price_per_lb is not None:
                landed_cost_per_lb = price_per_lb + (freight_per_kg / 2.20462)
            
            # Get or create CostMaster entry (one per SKU + vendor combination)
            cost_master, created = CostMaster.objects.get_or_create(
                wwi_product_code=item.sku,
                vendor=item.vendor,
                defaults={
                    'vendor_material': item.name,
                    'price_per_kg': price_per_kg,
                    'price_per_lb': price_per_lb,
                    'freight_per_kg': freight_per_kg,
                    'landed_cost_per_kg': landed_cost_per_kg,
                    'landed_cost_per_lb': landed_cost_per_lb,
                }
            )
            # Update if it already existed
            if not created:
                cost_master.vendor_material = item.name
                if price_per_kg is not None:
                    cost_master.price_per_kg = price_per_kg
                if price_per_lb is not None:
                    cost_master.price_per_lb = price_per_lb
                cost_master.freight_per_kg = freight_per_kg
                if landed_cost_per_kg is not None:
                    cost_master.landed_cost_per_kg = landed_cost_per_kg
                if landed_cost_per_lb is not None:
                    cost_master.landed_cost_per_lb = landed_cost_per_lb
                cost_master.save()
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def update(self, request, *args, **kwargs):
        """Update item and sync to CostMaster, creating history if price changed"""
        instance = self.get_object()
        old_price = instance.price
        old_pack_size = instance.pack_size
        old_unit = instance.unit_of_measure
        
        # Clean up the data
        data = request.data.copy()
        if 'description' in data and data['description'] == '':
            data['description'] = None
        if 'vendor' in data and data['vendor'] == '':
            data['vendor'] = None
        if 'pack_size' in data and (data['pack_size'] == '' or data['pack_size'] is None):
            data.pop('pack_size', None)
        if 'price' in data and (data['price'] == '' or data['price'] is None):
            data.pop('price', None)
        
        # Trim SKU and name if provided
        if 'sku' in data and isinstance(data['sku'], str):
            data['sku'] = data['sku'].strip()
        if 'name' in data and isinstance(data['name'], str):
            data['name'] = data['name'].strip()
        
        # Check for unique constraint violation before updating
        if 'sku' in data or 'vendor' in data:
            new_sku = data.get('sku', instance.sku)
            new_vendor = data.get('vendor', instance.vendor) or None
            # Check if another item with same SKU + vendor exists (excluding current instance)
            existing_item = Item.objects.filter(sku=new_sku, vendor=new_vendor).exclude(id=instance.id).first()
            if existing_item:
                return Response(
                    {'error': f'An item with SKU "{new_sku}" and vendor "{new_vendor or "None"}" already exists.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Update the item
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=data, partial=partial)
        if not serializer.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Serializer validation failed: {serializer.errors}')
            logger.error(f'Data being validated: {data}')
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        item = serializer.save()
        
        # Sync to CostMaster if vendor exists
        if item.vendor and (data.get('price') is not None or data.get('pack_size') is not None):
            # Find or create CostMaster entry
            cost_master, created = CostMaster.objects.get_or_create(
                wwi_product_code=item.sku,
                defaults={
                    'vendor_material': item.name,
                    'vendor': item.vendor,
                }
            )
            
            # Check if price changed
            price_changed = False
            new_price_per_kg = None
            new_price_per_lb = None
            
            if data.get('price') is not None:
                price = float(data['price'])
                unit_of_measure = data.get('unit_of_measure', item.unit_of_measure)
                
                if unit_of_measure == 'lbs':
                    new_price_per_lb = price
                    new_price_per_kg = price * 2.20462
                elif unit_of_measure == 'kg':
                    new_price_per_kg = price
                    new_price_per_lb = price / 2.20462
                else:
                    new_price_per_kg = price
                    new_price_per_lb = price
                
                # Check if price actually changed
                if (cost_master.price_per_kg != new_price_per_kg or 
                    cost_master.price_per_lb != new_price_per_lb):
                    price_changed = True
            
            # Update CostMaster
            if new_price_per_kg is not None:
                cost_master.price_per_kg = new_price_per_kg
            if new_price_per_lb is not None:
                cost_master.price_per_lb = new_price_per_lb
            if not created:
                cost_master.vendor_material = item.name
                cost_master.vendor = item.vendor
            
            # Recalculate landed cost
            freight_per_kg = cost_master.freight_per_kg or 0.0
            if cost_master.price_per_kg is not None:
                cost_master.landed_cost_per_kg = cost_master.price_per_kg + freight_per_kg
            if cost_master.price_per_lb is not None:
                cost_master.landed_cost_per_lb = cost_master.price_per_lb + (freight_per_kg / 2.20462)
            
            cost_master.save()
            
            # Create history record if price changed
            if price_changed:
                CostMasterHistory.objects.create(
                    cost_master=cost_master,
                    price_per_kg=cost_master.price_per_kg,
                    price_per_lb=cost_master.price_per_lb,
                    changed_by=request.user.username if hasattr(request.user, 'username') else 'system',
                    notes=f'Updated from Item {item.sku} - Price: {old_price} -> {item.price}, Pack Size: {old_pack_size} -> {item.pack_size}'
                )
        
        return Response(serializer.data)


class LotViewSet(viewsets.ModelViewSet):
    queryset = Lot.objects.select_related('item').all()
    serializer_class = LotSerializer
    
    @action(detail=False, methods=['get'])
    def lots_by_sku_vendor(self, request):
        """Get lot details for a specific SKU and vendor"""
        sku = request.query_params.get('sku', None)
        vendor = request.query_params.get('vendor', None)
        
        if not sku:
            return Response({'error': 'SKU parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get items with this SKU
        items = Item.objects.filter(sku=sku)
        if vendor:
            # Handle "Unknown" vendor - this means items with null/empty vendor
            if vendor == "Unknown":
                from django.db.models import Q
                items = items.filter(Q(vendor__isnull=True) | Q(vendor=''))
            else:
                items = items.filter(vendor=vendor)
        
        if not items.exists():
            return Response({'error': 'No items found for this SKU/vendor combination'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get all lots for these items
        item_ids = items.values_list('id', flat=True)
        lots = Lot.objects.filter(
            item_id__in=item_ids,
            status='accepted'
        ).select_related('item').order_by('-received_date')
        
        serializer = self.get_serializer(lots, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def inventory_details(self, request):
        """Get inventory details grouped hierarchically: SKU -> Vendor -> Lots"""
        from django.db.models import Sum, Q
        from django.db import connection
        from django.db.utils import OperationalError
        from .models import SalesOrderItem, ProductionBatchInput, Item, CostMaster, PurchaseOrder
        
        # Check if required tables exist
        try:
            with connection.cursor() as cursor:
                # Check Item table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_item'")
                if not cursor.fetchone():
                    return Response([])
                
                # Check Lot table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_lot'")
                if not cursor.fetchone():
                    return Response([])
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response([])
        
        try:
            # Get all items
            items = Item.objects.all()
        except (OperationalError, Exception) as e:
            import traceback
            traceback.print_exc()
            return Response([])
        
        inventory_data = []
        sku_master_data = {}  # Store master SKU aggregations
        
        # Pre-calculate item-level sales allocations using SalesOrderLot
        item_sales_allocations = {}
        try:
            # Check if SalesOrderLot table exists
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salesorderlot'")
                salesorderlot_exists = cursor.fetchone() is not None
            
            if salesorderlot_exists:
                for item_id in items.values_list('id', flat=True):
                    try:
                        # Sum allocations from SalesOrderLot for this item
                        total_allocated = SalesOrderLot.objects.filter(
                            sales_order_item__item_id=item_id,
                            sales_order_item__sales_order__status__in=['draft', 'allocated', 'shipped']
                        ).aggregate(
                            total=Sum('quantity_allocated')
                        )['total'] or 0.0
                        item_sales_allocations[item_id] = total_allocated
                    except Exception:
                        item_sales_allocations[item_id] = 0.0
            else:
                # Table doesn't exist, initialize all to 0
                for item_id in items.values_list('id', flat=True):
                    item_sales_allocations[item_id] = 0.0
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Initialize all to 0 if there's an error
            for item_id in items.values_list('id', flat=True):
                item_sales_allocations[item_id] = 0.0
        
        # Group items by SKU to avoid duplicates
        items_by_sku = {}
        for item in items:
            if item.sku not in items_by_sku:
                items_by_sku[item.sku] = []
            items_by_sku[item.sku].append(item)
        
        # For each unique SKU, get all vendors
        # CRITICAL: Process every SKU, even if it has no lots or vendors
        for sku, sku_items in items_by_sku.items():
            if not sku_items:
                continue  # Skip if no items (shouldn't happen)
            
            # DEBUG: Ensure we're processing this SKU
            print(f"Processing SKU: {sku} with {len(sku_items)} items")
            # Use the first item as representative for SKU-level data
            item = sku_items[0]
            # Get vendors for this SKU from CostMaster
            cost_masters = []
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_costmaster'")
                    if cursor.fetchone():
                        cost_masters = list(CostMaster.objects.filter(wwi_product_code=sku))
            except Exception:
                pass
            
            # Get all lots for all items with this SKU
            item_ids = [i.id for i in sku_items]
            try:
                item_lots = Lot.objects.filter(
                    item_id__in=item_ids,
                    status='accepted'
                ).select_related('item')
            except Exception:
                item_lots = []
            
            # Build a map of vendor -> lots by checking PO vendor
            vendor_lots_map = {}
            lots_without_vendor = []
            
            # Check if PurchaseOrder table exists
            po_table_exists = False
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_purchaseorder'")
                    po_table_exists = cursor.fetchone() is not None
            except Exception:
                pass
            
            for lot in item_lots:
                vendor_name = None
                if lot.po_number and po_table_exists:
                    try:
                        po = PurchaseOrder.objects.get(po_number=lot.po_number)
                        vendor_name = po.vendor_customer_name
                    except (PurchaseOrder.DoesNotExist, Exception):
                        pass
                
                if vendor_name:
                    if vendor_name not in vendor_lots_map:
                        vendor_lots_map[vendor_name] = []
                    vendor_lots_map[vendor_name].append(lot)
                else:
                    lots_without_vendor.append(lot)
            
            # Get unique vendors from all items with this SKU (this ensures all items are represented)
            # IMPORTANT: Include items with null/empty vendor as "Unknown"
            item_vendors = set()
            for sku_item in sku_items:
                vendor_name = sku_item.vendor if sku_item.vendor else "Unknown"
                item_vendors.add(vendor_name)
            
            # ALWAYS ensure we have at least one vendor entry (even if empty)
            if not item_vendors:
                item_vendors.add("Unknown")
            
            # Also get vendors from CostMaster and lots
            cost_master_vendors = set()
            for cm in cost_masters:
                if cm.vendor:
                    item_exists = Item.objects.filter(sku=sku, vendor=cm.vendor).exists()
                    if item_exists:
                        cost_master_vendors.add(cm.vendor)
            
            # Combine all vendor sources - items, cost master, and lots
            all_vendors = item_vendors.union(cost_master_vendors).union(set(vendor_lots_map.keys()))
            
            # If we have lots without vendor info, ensure "Unknown" is in the list
            if lots_without_vendor and "Unknown" not in all_vendors:
                all_vendors.add("Unknown")
            
            # CRITICAL: Ensure we always have at least one vendor entry for every SKU
            # This guarantees all items are shown, even if they have no vendor and no lots
            if not all_vendors:
                all_vendors = {"Unknown"}
            
            # Create an inventory entry for each vendor
            for vendor_name in sorted(all_vendors):
                # Get lots for this vendor
                vendor_lots = vendor_lots_map.get(vendor_name, [])
                
                # If this is the first vendor and there are lots without vendor, assign them here
                if vendor_name == sorted(all_vendors)[0] and lots_without_vendor:
                    vendor_lots.extend(lots_without_vendor)
                
                # Find the vendor-specific item - prioritize exact match
                vendor_item = Item.objects.filter(sku=sku, vendor=vendor_name).first()
                
                # If no exact match and vendor is "Unknown", use any item with this SKU
                if not vendor_item:
                    if vendor_name == "Unknown":
                        vendor_item = Item.objects.filter(sku=sku).first()
                    else:
                        # Try to find item with null/empty vendor for this SKU
                        vendor_item = Item.objects.filter(sku=sku, vendor__isnull=True).first() or \
                                     Item.objects.filter(sku=sku, vendor='').first() or \
                                     Item.objects.filter(sku=sku).first()
                
                # Always create entry - we know we have items for this SKU
                # If vendor_item is still None, use the first item from sku_items
                if not vendor_item:
                    vendor_item = sku_items[0]  # Use first item as fallback
                
                # Use the vendor-specific item if it exists, otherwise use the first item
                display_item = vendor_item if vendor_item else item
                
                # Aggregate quantities from lots
                total_quantity = sum(lot.quantity for lot in vendor_lots)
                quantity_remaining = sum(lot.quantity_remaining for lot in vendor_lots)
                
                # Get on_order from the vendor-specific item
                on_order = vendor_item.on_order if vendor_item else 0.0
                
                # Include on_order in total_quantity
                total_quantity = total_quantity + on_order
                
                # Calculate allocated to production (sum across all vendor lots)
                # Allocate materials when batch status is 'in_progress'
                allocated_to_production = 0.0
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_productionbatchinput'")
                        if cursor.fetchone():
                            allocated_to_production = ProductionBatchInput.objects.filter(
                                lot__in=vendor_lots,
                                batch__status__in=['in_progress', 'open']  # Support both old and new status values
                            ).aggregate(
                                total=Sum('quantity_used')
                            )['total'] or 0.0
                except Exception:
                    pass
                
                # Calculate on hold
                on_hold = sum(
                    lot.quantity_remaining for lot in vendor_lots 
                    if lot.status == 'on_hold' or lot.on_hold
                )
                
                # Available = quantity_remaining - production allocation - on_hold
                available = max(0.0, quantity_remaining - allocated_to_production - on_hold)
                
                # Get sales allocation - sum across all items with this SKU for this vendor
                allocated_to_sales = 0.0
                if vendor_item:
                    allocated_to_sales = item_sales_allocations.get(vendor_item.id, 0.0)
                else:
                    # Sum across all items with this SKU
                    for sku_item in sku_items:
                        allocated_to_sales += item_sales_allocations.get(sku_item.id, 0.0)
                
                # Create vendor-level inventory entry (nested under SKU)
                vendor_entry = {
                    'id': f"{sku}_{vendor_name}",  # Composite ID based on SKU+vendor
                    'item_id': display_item.id,
                    'item_sku': sku,
                    'description': display_item.name,
                    'vendor': vendor_name,
                    'pack_size': display_item.pack_size,
                    'pack_size_unit': display_item.unit_of_measure,
                    'total_quantity': total_quantity,
                    'allocated_to_sales': allocated_to_sales,
                    'allocated_to_production': allocated_to_production,
                    'on_hold': on_hold,
                    'on_order': on_order,
                    'available': available,
                    'quantity_remaining': quantity_remaining,
                    'lot_count': len(vendor_lots),
                    'item_type': display_item.item_type,
                    'level': 'vendor',  # Mark as vendor level
                }
                
                # Initialize or update master SKU aggregation
                if sku not in sku_master_data:
                    sku_master_data[sku] = {
                        'id': f"SKU_{sku}",  # Master SKU ID
                        'item_sku': sku,
                        'description': display_item.name,
                        'item_id': display_item.id,  # Use first item's ID for FPS lookup
                        'item_type': display_item.item_type,
                        'pack_size_unit': display_item.unit_of_measure,
                        'total_quantity': 0.0,
                        'allocated_to_sales': 0.0,
                        'allocated_to_production': 0.0,
                        'on_hold': 0.0,
                        'on_order': 0.0,
                        'available': 0.0,
                        'quantity_remaining': 0.0,
                        'lot_count': 0,
                        'vendor_count': 0,
                        'level': 'sku',  # Mark as SKU master level
                        'vendors': [],  # Store vendor entries
                    }
                
                # Aggregate to master SKU totals
                master = sku_master_data[sku]
                master['total_quantity'] += total_quantity
                master['allocated_to_sales'] += allocated_to_sales
                master['allocated_to_production'] += allocated_to_production
                master['on_hold'] += on_hold
                master['on_order'] += on_order
                master['available'] += available
                master['quantity_remaining'] += quantity_remaining
                master['lot_count'] += len(vendor_lots)
                master['vendor_count'] += 1
                master['vendors'].append(vendor_entry)
            
            # CRITICAL FALLBACK: If no vendor entries were created for this SKU, 
            # create a default entry to ensure the SKU appears in inventory
            # This handles edge cases where vendor matching fails
            if sku not in sku_master_data:
                # This ensures all SKUs are represented even if vendor logic fails
                first_item = sku_items[0]
                total_sales_alloc = sum(item_sales_allocations.get(i.id, 0.0) for i in sku_items)
                total_on_order = sum(getattr(i, 'on_order', 0.0) or 0.0 for i in sku_items)
                
                sku_master_data[sku] = {
                    'id': f"SKU_{sku}",
                    'item_sku': sku,
                    'description': first_item.name,
                    'item_id': first_item.id,
                    'item_type': first_item.item_type,
                    'pack_size_unit': first_item.unit_of_measure,
                    'total_quantity': total_on_order,  # Include on_order in total_quantity
                    'allocated_to_sales': total_sales_alloc,
                    'allocated_to_production': 0.0,
                    'on_hold': 0.0,
                    'on_order': total_on_order,
                    'available': 0.0,
                    'quantity_remaining': 0.0,
                    'lot_count': 0,
                    'vendor_count': 0,
                    'level': 'sku',
                    'vendors': [],
                }
        
        # Convert master SKU data to list and return
        for sku, master_data in sku_master_data.items():
            inventory_data.append(master_data)
        
        # DEBUG: Log what we're returning
        try:
            print(f"[INVENTORY DEBUG] Returning {len(inventory_data)} SKU entries")
            if inventory_data:
                print(f"[INVENTORY DEBUG] First entry: SKU={inventory_data[0].get('item_sku')}, level={inventory_data[0].get('level')}")
            else:
                print(f"[INVENTORY DEBUG] WARNING: No inventory data to return!")
                print(f"[INVENTORY DEBUG] Items in DB: {items.count()}, SKUs grouped: {len(items_by_sku)}")
        except Exception:
            pass
        
        try:
            return Response(inventory_data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response([])
    
    def create(self, request, *args, **kwargs):
        # Get the item to check if it's a raw material
        item_id = request.data.get('item_id')
        item = None
        if item_id:
            try:
                item = Item.objects.get(id=item_id)
            except Item.DoesNotExist:
                pass
        
        # Only generate internal lot number for finished goods
        # Raw materials should use vendor lot number only
        lot_number = None
        if item and item.item_type == 'finished_good':
            lot_number = generate_lot_number()
        
        # For raw materials, vendor_lot_number is required
        if item and item.item_type == 'raw_material':
            vendor_lot_number = request.data.get('vendor_lot_number')
            # Handle None, empty string, or whitespace-only strings
            if vendor_lot_number is None:
                vendor_lot_number = ''
            elif isinstance(vendor_lot_number, str):
                vendor_lot_number = vendor_lot_number.strip()
            else:
                vendor_lot_number = str(vendor_lot_number).strip()
            
            if not vendor_lot_number:
                return Response(
                    {'error': 'Vendor lot number is required for raw materials'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Use vendor lot number as the lot number for raw materials
            lot_number = vendor_lot_number
        
        # Get lot_status from request data (renamed to avoid shadowing status module)
        lot_status = request.data.get('status', 'accepted')
        
        # Create the lot
        serializer_data = {
            **request.data,
            'status': lot_status,
        }
        
        # Only set lot_number if we have one
        if lot_number:
            serializer_data['lot_number'] = lot_number
        elif not item:
            # Fallback: if item doesn't exist, generate a lot number anyway
            # (shouldn't happen, but handle gracefully)
            # Only generate for non-raw materials (can't check item_type if item doesn't exist, but this is a fallback)
            lot_number = generate_lot_number()
            serializer_data['lot_number'] = lot_number
        
        serializer = self.get_serializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)
        lot = serializer.save()
        
        # For raw materials, ensure vendor_lot_number is saved
        if item and item.item_type == 'raw_material':
            vendor_lot_number = request.data.get('vendor_lot_number')
            # Handle None, empty string, or whitespace-only strings
            if vendor_lot_number is None:
                vendor_lot_number = ''
            elif isinstance(vendor_lot_number, str):
                vendor_lot_number = vendor_lot_number.strip()
            else:
                vendor_lot_number = str(vendor_lot_number).strip()
            
            # Always save vendor_lot_number for raw materials (it should match lot_number)
            if vendor_lot_number:
                lot.vendor_lot_number = vendor_lot_number
                # Ensure lot_number matches vendor_lot_number for raw materials
                if lot.lot_number != vendor_lot_number:
                    lot.lot_number = vendor_lot_number
                lot.save()
        
        # Set quantity_remaining based on lot_status
        if lot_status == 'accepted':
            lot.quantity_remaining = lot.quantity
        elif lot_status == 'rejected':
            lot.quantity_remaining = 0
        elif lot_status == 'on_hold':
            lot.quantity_remaining = 0
            lot.on_hold = True
        lot.save()
        
        # Only create inventory transaction for accepted lots
        if lot_status == 'accepted':
            InventoryTransaction.objects.create(
                transaction_type='receipt',
                lot=lot,
                quantity=lot.quantity,
            )
            
            # Update on_order and PO item if PO number is provided
            if lot.po_number:
                try:
                    from .models import PurchaseOrder, PurchaseOrderItem
                    po = PurchaseOrder.objects.get(po_number=lot.po_number)
                    for po_item in po.items.all():
                        if po_item.item == lot.item:
                            # Update quantity received
                            po_item.quantity_received += lot.quantity
                            po_item.save()
                            
                            # Reduce on_order by the quantity received
                            item = lot.item
                            item.on_order = max(0, (item.on_order or 0) - lot.quantity)
                            item.save()
                            
                            # If quantity received is less than ordered, keep remaining on_order
                            # The outstanding balance stays on_order until fully received
                            remaining_ordered = po_item.quantity_ordered - po_item.quantity_received
                            if remaining_ordered > 0:
                                # Outstanding quantity remains on_order
                                pass
                            break
                    
                    # Check if all items are fully received
                    # Use a small tolerance for floating point comparison
                    all_received = True
                    for po_item in po.items.all():
                        # Allow small tolerance (0.01) for floating point precision
                        if po_item.quantity_received < (po_item.quantity_ordered - 0.01):
                            all_received = False
                            break
                    
                    # If all items are fully received, update PO status to 'received'
                    if all_received and po.status == 'issued':
                        po.status = 'received'
                        po.save()
                except PurchaseOrder.DoesNotExist:
                    pass
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True, methods=['post'], url_path='reverse-check-in', url_name='reverse-check-in')
    def reverse_check_in(self, request, pk=None):
        try:
            lot = self.get_object()
        except Exception as e:
            return Response(
                {'error': f'Lot not found: {str(e)}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Store lot info before any operations that might trigger foreign key checks
        lot_id = lot.id
        lot_number = lot.lot_number
        try:
            item_sku = lot.item.sku if lot.item else None
        except Exception:
            item_sku = None
        quantity = lot.quantity
        
        # Validate that lot hasn't been used
        if lot.quantity_remaining < lot.quantity:
            return Response(
                {'error': 'Cannot reverse check-in: lot has been partially or fully used'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get item_id before any operations that might trigger foreign key checks
        try:
            item_id = lot.item_id if hasattr(lot, 'item_id') else None
            po_number = lot.po_number if hasattr(lot, 'po_number') else None
        except Exception:
            item_id = None
            po_number = None
        
        # Reverse the inventory transaction (if one exists) using raw SQL
        from django.db import connection
        from django.utils import timezone
        
        try:
            with connection.cursor() as cursor:
                # Check if receipt transaction exists
                cursor.execute("""
                    SELECT id FROM erp_core_inventorytransaction 
                    WHERE lot_id = ? AND transaction_type = 'receipt'
                    LIMIT 1
                """, [lot_id])
                receipt_transaction = cursor.fetchone()
                
                if receipt_transaction:
                    # Create reverse transaction using raw SQL
                    cursor.execute("""
                        INSERT INTO erp_core_inventorytransaction 
                        (transaction_type, lot_id, quantity, notes, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, ['adjustment', lot_id, -quantity, 'Reverse check-in', timezone.now()])
            
            # Update PO if it exists using raw SQL
            if po_number:
                try:
                    with connection.cursor() as cursor:
                        # Get PO ID
                        cursor.execute("SELECT id FROM erp_core_purchaseorder WHERE po_number = ?", [po_number])
                        po_result = cursor.fetchone()
                        if po_result:
                            po_id = po_result[0]
                            
                            # Update PO item quantity_received
                            # First, get the current quantity_received to know how much to restore
                            if item_id:
                                cursor.execute("""
                                    SELECT quantity_received 
                                    FROM erp_core_purchaseorderitem 
                                    WHERE purchase_order_id = ? AND item_id = ?
                                """, [po_id, item_id])
                                result = cursor.fetchone()
                                current_received = result[0] if result else 0.0
                                
                                # Calculate how much will actually be reversed (can't go below 0)
                                amount_to_reverse = min(quantity, current_received)
                                
                                # Update quantity_received
                                cursor.execute("""
                                    UPDATE erp_core_purchaseorderitem 
                                    SET quantity_received = MAX(0, quantity_received - ?)
                                    WHERE purchase_order_id = ? AND item_id = ?
                                """, [quantity, po_id, item_id])
                                
                                # Only restore on_order by the amount that was actually reversed
                                if amount_to_reverse > 0:
                                    cursor.execute("""
                                        UPDATE erp_core_item 
                                        SET on_order = on_order + ?
                                        WHERE id = ?
                                    """, [amount_to_reverse, item_id])
                            
                            # Update PO status back to 'issued' if it was 'received'
                            cursor.execute("""
                                UPDATE erp_core_purchaseorder 
                                SET status = 'issued'
                                WHERE id = ? AND status = 'received'
                            """, [po_id])
                except Exception:
                    pass  # PO might not exist, that's okay
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Don't return error here - continue with deletion
        
        # Store lot info for response (already stored above, but create response object)
        lot_info = {
            'lot_number': lot_number,
            'item_sku': item_sku,
            'quantity': quantity
        }
        
        # Check for related objects that might prevent deletion using raw SQL only
        from django.db import connection
        from django.db.utils import OperationalError
        
        # Check if lot is used in sales orders using raw SQL
        has_sales_allocations = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salesorderlot'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM erp_core_salesorderlot WHERE lot_id = ?", [lot_id])
                    result = cursor.fetchone()
                    has_sales_allocations = result[0] > 0 if result else False
        except Exception:
            pass
        
        # Check if lot is used in production batches using raw SQL
        has_production_usage = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_productionbatchinput'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM erp_core_productionbatchinput WHERE lot_id = ?", [lot_id])
                    result = cursor.fetchone()
                    has_production_usage = result[0] > 0 if result else False
        except Exception:
            pass
        
        if has_sales_allocations:
            return Response(
                {'error': 'Cannot reverse check-in: lot is allocated to sales orders. Please remove allocations first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if has_production_usage:
            return Response(
                {'error': 'Cannot reverse check-in: lot is used in production batches. Cannot reverse lots that have been used in production.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete related inventory transactions first using raw SQL to avoid ORM foreign key checks
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM erp_core_inventorytransaction WHERE lot_id = ?", [lot_id])
        except Exception:
            pass  # Table might not exist, that's okay
        
        # Delete related SalesOrderLot entries if table exists
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salesorderlot'")
                if cursor.fetchone():
                    cursor.execute("DELETE FROM erp_core_salesorderlot WHERE lot_id = ?", [lot_id])
        except Exception:
            pass  # Table doesn't exist or error, that's okay
        
        # Delete related ProductionBatchInput entries if table exists
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_productionbatchinput'")
                if cursor.fetchone():
                    cursor.execute("DELETE FROM erp_core_productionbatchinput WHERE lot_id = ?", [lot_id])
        except Exception:
            pass  # Table doesn't exist or error, that's okay
        
        # Now delete the lot using raw SQL ONLY to avoid Django ORM foreign key checks
        # We never use lot.delete() because it will check foreign keys to tables that may not exist
        try:
            with connection.cursor() as cursor:
                # Temporarily disable foreign key checks
                cursor.execute("PRAGMA foreign_keys = OFF")
                # Delete the lot
                cursor.execute("DELETE FROM erp_core_lot WHERE id = ?", [lot_id])
                # Re-enable foreign key checks
                cursor.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Error deleting lot: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response({
            'message': 'Check-in reversed successfully',
            'lot': lot_info
        }, status=status.HTTP_200_OK)


class ProductionBatchViewSet(viewsets.ModelViewSet):
    queryset = ProductionBatch.objects.select_related('finished_good_item').prefetch_related(
        'inputs__lot__item', 'outputs__lot__item'
    ).all()
    serializer_class = ProductionBatchSerializer
    
    def create(self, request, *args, **kwargs):
        """Handle batch creation for both production and repack batches"""
        data = request.data.copy()
        inputs_data = data.pop('inputs', [])
        outputs_data = data.pop('outputs', [])
        batch_type = data.get('batch_type', 'production')
        
        # Convert production_date from date string to datetime if needed
        if 'production_date' in data and isinstance(data['production_date'], str):
            from django.utils.dateparse import parse_date, parse_datetime
            # Try parsing as datetime first
            parsed = parse_datetime(data['production_date'])
            if not parsed:
                # Try parsing as date and convert to datetime
                date_obj = parse_date(data['production_date'])
                if date_obj:
                    # Create datetime at noon in local timezone (CST) to avoid timezone conversion issues
                    # This ensures the date stays the same regardless of timezone
                    # We use noon instead of midnight to avoid edge cases with DST
                    from datetime import time as dt_time
                    local_tz = timezone.get_current_timezone()
                    local_midday = local_tz.localize(datetime.combine(date_obj, dt_time(12, 0, 0)))
                    parsed = local_midday
            if parsed:
                data['production_date'] = parsed
            else:
                # If parsing fails, use current time
                data['production_date'] = timezone.now()
        
        # Auto-generate batch number if not provided or if it already exists
        if 'batch_number' not in data or not data.get('batch_number'):
            data['batch_number'] = generate_batch_number(batch_type)
        else:
            # Check if the provided batch number already exists
            existing_batch = ProductionBatch.objects.filter(batch_number=data['batch_number']).first()
            if existing_batch:
                # Generate a new unique batch number
                data['batch_number'] = generate_batch_number(batch_type)
        
        # Ensure finished_good_item_id is set (required for both production and repack)
        if 'finished_good_item_id' not in data or not data.get('finished_good_item_id'):
            if batch_type == 'production':
                return Response(
                    {'error': 'finished_good_item_id is required for production batches'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # For repack, we'll set it from the input lots below
        
        # For repack batches, ensure we have the item and inputs
        if batch_type == 'repack':
            if not inputs_data:
                return Response(
                    {'error': 'Repack batches require at least one input lot'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the item from the first input lot
            try:
                first_lot = Lot.objects.get(id=inputs_data[0]['lot_id'])
                item = first_lot.item
                
                # Validate that all input lots are for the same item
                for input_data in inputs_data:
                    lot = Lot.objects.get(id=input_data['lot_id'])
                    if lot.item.id != item.id:
                        return Response(
                            {'error': 'All input lots must be for the same item in a repack batch'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                # Set the finished_good_item to the item (even though it's not a finished good)
                data['finished_good_item_id'] = item.id
            except Lot.DoesNotExist:
                return Response(
                    {'error': 'Invalid lot ID in inputs'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate inputs before creating batch
        from .models import ProductionBatchInput, ProductionBatchOutput, InventoryTransaction
        quantity_produced = round(float(data.get('quantity_produced', 0)), 2)  # Round to 2 decimal places
        data['quantity_produced'] = quantity_produced
        total_input_quantity_in_lbs = 0.0  # Track total in lbs for validation
        
        # First pass: validate all inputs and calculate total
        for input_data in inputs_data:
            lot_id = input_data.get('lot_id')
            quantity_used = round(float(input_data.get('quantity_used', 0)), 2)  # Round to 2 decimal places
            
            if not lot_id or quantity_used <= 0:
                return Response(
                    {'error': 'Invalid input data: lot_id and quantity_used are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                lot = Lot.objects.get(id=lot_id)
                if lot.quantity_remaining < quantity_used:
                    return Response(
                        {'error': f'Insufficient quantity in lot {lot.lot_number}. Available: {lot.quantity_remaining}, Requested: {quantity_used}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Convert quantity to lbs for validation (quantity_produced is in lbs)
                quantity_used_in_lbs = quantity_used
                if lot.item.unit_of_measure == 'kg':
                    quantity_used_in_lbs = quantity_used * 2.20462  # Convert kg to lbs
                elif lot.item.unit_of_measure == 'ea':
                    # For "each" items, assume 1:1 ratio (may need adjustment based on business rules)
                    quantity_used_in_lbs = quantity_used
                
                total_input_quantity_in_lbs += quantity_used_in_lbs
                
            except Lot.DoesNotExist:
                return Response(
                    {'error': f'Lot with id {lot_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Validate that total input quantity equals quantity to produce (with tolerance for floating point precision)
        tolerance = 0.1  # Increased tolerance to account for conversion rounding differences
        if abs(total_input_quantity_in_lbs - quantity_produced) > tolerance:
            return Response(
                {
                    'error': f'Quantity mismatch: Total quantity used ({total_input_quantity_in_lbs:.2f} lbs) must equal quantity to produce ({quantity_produced:.2f} lbs)'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the batch
        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Serializer validation failed: {serializer.errors}')
            logger.error(f'Data being validated: {data}')
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        batch = serializer.save()
        
        # Create inputs (second pass: actually create them - validation already done above)
        for input_data in inputs_data:
            lot_id = input_data.get('lot_id')
            quantity_used = round(float(input_data.get('quantity_used', 0)), 2)  # Round to 2 decimal places
            
            # Get lot (already validated in first pass)
            lot = Lot.objects.get(id=lot_id)
            
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                quantity_used=quantity_used
            )
            
            # Create inventory transaction for input (reduce quantity) - round to 2 decimal places
            rounded_quantity = round(quantity_used, 2)
            InventoryTransaction.objects.create(
                transaction_type='production_input',
                lot=lot,
                quantity=round(-rounded_quantity, 2),
                notes=f'Batch {batch.batch_number} input',
                reference_number=batch.batch_number
            )
            
            # Update lot quantity_remaining - round to 2 decimal places
            lot.quantity_remaining = round(lot.quantity_remaining - rounded_quantity, 2)
            lot.save()
        
        # Validate that total input quantity equals quantity to produce (with tolerance for floating point)
        tolerance = 0.01
        if abs(total_input_quantity_in_lbs - quantity_produced) > tolerance:
            batch.delete()
            return Response(
                {
                    'error': f'Quantity mismatch: Total quantity used ({total_input_quantity_in_lbs:.2f} lbs) must equal quantity to produce ({quantity_produced:.2f} lbs)'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create outputs
        if batch_type == 'repack':
            # For repack, create a new lot with the same item
            if not outputs_data:
                # Auto-create output lot if not provided
                output_quantity = batch.quantity_produced if batch.quantity_produced > 0 else total_input_quantity
                item = batch.finished_good_item
                
                # Generate new lot number
                lot_number = generate_lot_number()
                
                # Create new lot
                new_lot = Lot.objects.create(
                    lot_number=lot_number,
                    item=item,
                    quantity=output_quantity,
                    quantity_remaining=output_quantity,
                    received_date=timezone.now(),
                    status='accepted'
                )
                
                # Create output record
                ProductionBatchOutput.objects.create(
                    batch=batch,
                    lot=new_lot,
                    quantity_produced=output_quantity
                )
                
                # Create inventory transaction for output (add quantity)
                InventoryTransaction.objects.create(
                    transaction_type='production_output',
                    lot=new_lot,
                    quantity=output_quantity,
                    notes=f'Repack batch {batch.batch_number} output',
                    reference_number=batch.batch_number
                )
            else:
                # Use provided outputs
                for output_data in outputs_data:
                    lot_id = output_data.get('lot_id')
                    quantity_produced = float(output_data.get('quantity_produced', 0))
                    
                    if not lot_id or quantity_produced <= 0:
                        batch.delete()
                        return Response(
                            {'error': 'Invalid output data: lot_id and quantity_produced are required'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    try:
                        lot = Lot.objects.get(id=lot_id)
                        ProductionBatchOutput.objects.create(
                            batch=batch,
                            lot=lot,
                            quantity_produced=quantity_produced
                        )
                        
                        # Create inventory transaction
                        InventoryTransaction.objects.create(
                            transaction_type='production_output',
                            lot=lot,
                            quantity=quantity_produced,
                            notes=f'Batch {batch.batch_number} output',
                            reference_number=batch.batch_number
                        )
                    except Lot.DoesNotExist:
                        batch.delete()
                        return Response(
                            {'error': f'Lot with id {lot_id} not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )
        else:
            # For production batches, use provided outputs (existing behavior)
            for output_data in outputs_data:
                lot_id = output_data.get('lot_id')
                quantity_produced = round(float(output_data.get('quantity_produced', 0)), 2)  # Round to 2 decimal places
                
                if lot_id and quantity_produced > 0:
                    try:
                        lot = Lot.objects.get(id=lot_id)
                        ProductionBatchOutput.objects.create(
                            batch=batch,
                            lot=lot,
                            quantity_produced=quantity_produced
                        )
                        
                        InventoryTransaction.objects.create(
                            transaction_type='production_output',
                            lot=lot,
                            quantity=round(quantity_produced, 2),
                            notes=f'Batch {batch.batch_number} output',
                            reference_number=batch.batch_number
                        )
                    except Lot.DoesNotExist:
                        pass  # Allow production batches to be created without outputs initially
        
        # Return the created batch
        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """Update batch and handle status changes"""
        from .models import ProductionBatchInput, ProductionBatchOutput, InventoryTransaction
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_status = instance.status
        data = request.data.copy()
        new_status = data.get('status', old_status)
        
        # Handle inputs update if provided
        inputs_data = data.pop('inputs', None)
        if inputs_data is not None:
            # Round quantity_produced if provided
            if 'quantity_produced' in data:
                data['quantity_produced'] = round(float(data['quantity_produced']), 2)
            
            # Delete existing inputs and restore lot quantities
            for existing_input in instance.inputs.all():
                lot = existing_input.lot
                # Restore the quantity that was used
                lot.quantity_remaining = round(lot.quantity_remaining + existing_input.quantity_used, 2)
                lot.save()
                # Delete the old input
                existing_input.delete()
            
            # Create new inputs with rounded quantities
            for input_data in inputs_data:
                lot_id = input_data.get('lot_id')
                quantity_used = round(float(input_data.get('quantity_used', 0)), 2)
                
                if lot_id and quantity_used > 0:
                    try:
                        lot = Lot.objects.get(id=lot_id)
                        if lot.quantity_remaining < quantity_used:
                            return Response(
                                {'error': f'Insufficient quantity in lot {lot.lot_number}. Available: {lot.quantity_remaining}, Requested: {quantity_used}'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        ProductionBatchInput.objects.create(
                            batch=instance,
                            lot=lot,
                            quantity_used=quantity_used
                        )
                        
                        # Create inventory transaction for input (reduce quantity)
                        InventoryTransaction.objects.create(
                            transaction_type='production_input',
                            lot=lot,
                            quantity=round(-quantity_used, 2),
                            notes=f'Batch {instance.batch_number} input (adjusted)',
                            reference_number=instance.batch_number
                        )
                        
                        # Update lot quantity_remaining
                        lot.quantity_remaining = round(lot.quantity_remaining - quantity_used, 2)
                        lot.save()
                    except Lot.DoesNotExist:
                        return Response(
                            {'error': f'Lot with id {lot_id} not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )
        
        # Update the batch
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        batch = serializer.save()
        
        # If status changed to 'closed', create output lots if they don't exist
        if old_status != 'closed' and new_status == 'closed':
            # Check if batch has outputs
            if not batch.outputs.exists():
                # Create output lot for production batches
                if batch.batch_type == 'production':
                    # Use quantity_actual if available, otherwise quantity_produced - round to 2 decimal places
                    output_quantity = round(batch.quantity_actual if batch.quantity_actual and batch.quantity_actual > 0 else batch.quantity_produced, 2)
                    item = batch.finished_good_item
                    
                    # Generate new lot number
                    lot_number = generate_lot_number()
                    
                    # Create new lot
                    new_lot = Lot.objects.create(
                        lot_number=lot_number,
                        item=item,
                        quantity=output_quantity,
                        quantity_remaining=output_quantity,
                        received_date=timezone.now(),
                        status='accepted'
                    )
                    
                    # Create output record
                    ProductionBatchOutput.objects.create(
                        batch=batch,
                        lot=new_lot,
                        quantity_produced=output_quantity
                    )
                    
                    # Create inventory transaction for output (add quantity)
                    InventoryTransaction.objects.create(
                        transaction_type='production_output',
                        lot=new_lot,
                        quantity=round(output_quantity, 2),
                        notes=f'Production batch {batch.batch_number} output',
                        reference_number=batch.batch_number
                    )
                    
                    # Log the created lot for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f'Created output lot {new_lot.lot_number} for batch {batch.batch_number}: item={item.sku}, quantity={output_quantity}, status={new_lot.status}')
        
        # Return the updated batch
        serializer = self.get_serializer(batch)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='pdf', url_name='pdf')
    def generate_pdf(self, request, pk=None):
        """Generate a PDF batch ticket for printing"""
        from django.http import HttpResponse
        from io import BytesIO
        
        batch = self.get_object()
        
        try:
            # Try to import reportlab
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        except ImportError:
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'reportlab is not installed. Please install it with: pip install reportlab'},
                status=500
            )
        
        # Create a BytesIO buffer for the PDF
        buffer = BytesIO()
        
        # Create filename with status prefix for document title
        status_prefix = batch.status.replace('_', '-')  # Convert in_progress to in-progress
        filename = f"{status_prefix}({batch.batch_number}).pdf"
        doc_title = f"{status_prefix.upper()}({batch.batch_number})"
        
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter, 
            topMargin=0.5*inch, 
            bottomMargin=0.5*inch,
            title=doc_title,
            author="WWI ERP System"
        )
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#000000'),
            spaceAfter=6,
            alignment=TA_LEFT
        )
        normal_style = styles['Normal']
        
        # Title
        elements.append(Paragraph("BATCH TICKET", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Determine the base unit from finished good item (default to lbs)
        # This is the unit that was selected for "quantity to produce"
        base_unit = batch.finished_good_item.unit_of_measure or 'lbs'
        
        # Helper function to convert quantity from lbs (stored in DB) to base unit
        # quantity_produced, quantity_actual, variance, wastes, spills are all stored in lbs
        def convert_from_lbs_to_base(quantity_in_lbs):
            if base_unit == 'lbs' or base_unit == 'ea':
                return quantity_in_lbs
            elif base_unit == 'kg':
                # Convert from lbs to kg
                return quantity_in_lbs / 2.20462
            return quantity_in_lbs
        
        # Convert quantity_produced to base unit for display
        quantity_produced_display = convert_from_lbs_to_base(batch.quantity_produced)
        
        # Batch Information
        batch_data = [
            ['Batch Number:', batch.batch_number],
            ['Type:', batch.get_batch_type_display()],
            ['Finished Good:', f"{batch.finished_good_item.name} ({batch.finished_good_item.sku})"],
            ['Quantity to Produce:', f"{quantity_produced_display:.2f} {base_unit}"],
            ['Production Date:', batch.production_date.strftime('%m/%d/%Y') if batch.production_date else 'N/A'],
            ['Status:', batch.get_status_display()],
        ]
        
        # Add closed batch information if batch is closed (convert to base unit)
        if batch.status == 'closed':
            if batch.quantity_actual:
                qty_actual = convert_from_lbs_to_base(batch.quantity_actual)
                batch_data.append(['Quantity Actual:', f"{qty_actual:.2f} {base_unit}"])
            if batch.variance is not None:
                variance = convert_from_lbs_to_base(batch.variance)
                variance_sign = '+' if variance >= 0 else ''
                batch_data.append(['Variance:', f"{variance_sign}{variance:.2f} {base_unit}"])
            if batch.wastes:
                wastes = convert_from_lbs_to_base(batch.wastes)
                batch_data.append(['Wastes:', f"{wastes:.2f} {base_unit}"])
            if batch.spills:
                spills = convert_from_lbs_to_base(batch.spills)
                batch_data.append(['Spills:', f"{spills:.2f} {base_unit}"])
            if batch.closed_date:
                batch_data.append(['Closed Date:', batch.closed_date.strftime('%m/%d/%Y %I:%M %p') if batch.closed_date else 'N/A'])
        
        # Parse QC information from notes if present
        qc_info = {}
        if batch.notes:
            import re
            # Look for QC Parameters, QC Actual, and QC Initials in notes
            # Handle both single line and multi-line formats
            qc_params_match = re.search(r'QC Parameters:\s*(.+?)(?:\n|QC Actual:|$)', batch.notes, re.IGNORECASE | re.DOTALL)
            qc_actual_match = re.search(r'QC Actual:\s*(.+?)(?:\n|QC Initials:|$)', batch.notes, re.IGNORECASE | re.DOTALL)
            qc_initials_match = re.search(r'QC Initials:\s*(.+?)(?:\n|$)', batch.notes, re.IGNORECASE | re.DOTALL)
            
            if qc_params_match:
                qc_info['parameters'] = qc_params_match.group(1).strip()
            if qc_actual_match:
                qc_info['actual'] = qc_actual_match.group(1).strip()
            if qc_initials_match:
                qc_info['initials'] = qc_initials_match.group(1).strip()
            
            # Only add notes if it's not just QC info (to avoid duplication)
            # Check if notes contains other content besides QC info
            notes_without_qc = batch.notes
            if qc_info.get('parameters'):
                notes_without_qc = re.sub(r'QC Parameters:.*?(?:\n|QC Actual:|$)', '', notes_without_qc, flags=re.IGNORECASE | re.DOTALL)
            if qc_info.get('actual'):
                notes_without_qc = re.sub(r'QC Actual:.*?(?:\n|QC Initials:|$)', '', notes_without_qc, flags=re.IGNORECASE | re.DOTALL)
            if qc_info.get('initials'):
                notes_without_qc = re.sub(r'QC Initials:.*?(?:\n|$)', '', notes_without_qc, flags=re.IGNORECASE | re.DOTALL)
            
            notes_without_qc = notes_without_qc.strip()
            if notes_without_qc:
                batch_data.append(['Notes:', notes_without_qc])
        
        batch_table = Table(batch_data, colWidths=[2*inch, 4.5*inch])
        batch_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(batch_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Input Lots
        elements.append(Paragraph("INPUT MATERIALS", heading_style))
        if batch.inputs.exists():
            input_data = [['Lot Number', 'Item', 'SKU', 'Vendor Lot', f'Quantity Used ({base_unit})']]
            for batch_input in batch.inputs.select_related('lot__item').all():
                lot = batch_input.lot
                item = lot.item
                vendor_lot = lot.vendor_lot_number or lot.lot_number
                # Convert quantity to base unit
                # quantity_used is stored in the item's native unit in the DB
                # We need to convert it to lbs first, then to base unit
                item_unit = item.unit_of_measure or 'lbs'
                quantity_in_lbs = batch_input.quantity_used
                if item_unit == 'kg':
                    # Convert from kg to lbs
                    quantity_in_lbs = batch_input.quantity_used * 2.20462
                # Now convert from lbs to base unit
                quantity_in_base = convert_from_lbs_to_base(quantity_in_lbs)
                input_data.append([
                    lot.lot_number,
                    item.name,
                    item.sku,
                    vendor_lot,
                    f"{quantity_in_base:.2f}"
                ])
            
            input_table = Table(input_data, colWidths=[1*inch, 1.5*inch, 1*inch, 1*inch, 1.2*inch])
            input_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            ]))
            elements.append(input_table)
        else:
            elements.append(Paragraph("No input materials", normal_style))
        
        elements.append(Spacer(1, 0.3*inch))
        
        # Output Lots (if any)
        if batch.outputs.exists():
            elements.append(Paragraph("OUTPUT LOTS", heading_style))
            output_data = [['Lot Number', 'Item', 'SKU', f'Quantity Produced ({base_unit})']]
            for batch_output in batch.outputs.select_related('lot__item').all():
                lot = batch_output.lot
                item = lot.item
                # Convert quantity to base unit
                # quantity_produced is stored in lbs in the DB
                quantity_in_base = convert_from_lbs_to_base(batch_output.quantity_produced)
                output_data.append([
                    lot.lot_number,
                    item.name,
                    item.sku,
                    f"{quantity_in_base:.2f}"
                ])
            
            output_table = Table(output_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 1.5*inch])
            output_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            ]))
            elements.append(output_table)
        
        # Add Quality Control section for closed batches
        if batch.status == 'closed' and qc_info:
            elements.append(Spacer(1, 0.3*inch))
            elements.append(Paragraph("QUALITY CONTROL", heading_style))
            qc_data = []
            if qc_info.get('parameters'):
                qc_data.append(['QC Parameters:', qc_info['parameters']])
            if qc_info.get('actual'):
                qc_data.append(['QC Actual:', qc_info['actual']])
            if qc_info.get('initials'):
                qc_data.append(['QC Initials:', qc_info['initials']])
            
            if qc_data:
                qc_table = Table(qc_data, colWidths=[2*inch, 4.5*inch])
                qc_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                elements.append(qc_table)
        
        # Build PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer and write it to the response
        pdf = buffer.getvalue()
        buffer.close()
        
        # Create HTTP response with PDF
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        # Set the title for browser tab display
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        batch = self.get_object()
        
        try:
            # Store batch number for error messages
            batch_number = batch.batch_number
            
            # CRITICAL: Get all lot IDs BEFORE doing anything else
            # Get output lot IDs and lot objects before deleting anything
            output_lot_ids = []
            output_lots_to_delete = []
            try:
                for batch_output in batch.outputs.all():
                    lot_id = batch_output.lot_id
                    if lot_id:
                        output_lot_ids.append(lot_id)
                        try:
                            lot = Lot.objects.get(id=lot_id)
                            output_lots_to_delete.append(lot)
                        except Lot.DoesNotExist:
                            pass
            except Exception:
                pass
            
            # Get input lot IDs before processing
            input_lot_ids = list(batch.inputs.values_list('lot_id', flat=True))
            
            # Restore input lot quantities first
            for batch_input in batch.inputs.all():
                try:
                    # Use select_related or get the lot directly
                    lot_id = batch_input.lot_id
                    if lot_id:
                        lot = Lot.objects.get(id=lot_id)
                        # Restore the quantity that was used
                        lot.quantity_remaining += batch_input.quantity_used
                        lot.save()
                except (Lot.DoesNotExist, AttributeError, ValueError):
                    # Lot was already deleted or doesn't exist, skip
                    pass
            
            # Delete output lots FIRST (these were created by the batch)
            # This must happen before deleting the batch to avoid foreign key issues
            from .models import InventoryTransaction
            
            # Delete all transactions for output lots first
            if output_lot_ids:
                InventoryTransaction.objects.filter(lot_id__in=output_lot_ids).delete()
            
            # Then delete the output lots themselves
            for lot in output_lots_to_delete:
                try:
                    lot.delete()
                except Exception:
                    pass
            
            # Reverse all inventory transactions for this batch
            # Find transactions by looking at lots associated with batch inputs/outputs
            
            # Find transactions for input lots that reference this batch in notes
            # Note: output lots are already deleted, so we only need to reverse input lot transactions
            if input_lot_ids:
                transactions = InventoryTransaction.objects.filter(
                    lot_id__in=input_lot_ids,
                    notes__icontains=f'batch {batch_number}'
                )
                
                for transaction in transactions:
                    try:
                        # Get lot_id directly from the transaction
                        lot_id = transaction.lot_id
                        if not lot_id:
                            continue
                        
                        # Check if lot still exists before creating reverse transaction
                        try:
                            lot = Lot.objects.get(id=lot_id)
                            InventoryTransaction.objects.create(
                                transaction_type='adjustment',
                                lot=lot,
                                quantity=-transaction.quantity,
                                notes=f'Reverse batch {batch_number}',
                            )
                        except Lot.DoesNotExist:
                            # Lot doesn't exist anymore, skip
                            pass
                    except (AttributeError, ValueError, TypeError) as e:
                        # Handle any field access errors
                        import traceback
                        print(f"Error processing transaction {transaction.id}: {e}")
                        traceback.print_exc()
                        pass
            
            # Delete the batch (this will cascade delete ProductionBatchInput and ProductionBatchOutput records)
            batch.delete()
            
            return Response({'message': 'Batch ticket reversed successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()
            return Response(
                {'error': f'Failed to reverse batch: {error_msg}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FormulaViewSet(viewsets.ModelViewSet):
    queryset = Formula.objects.select_related('finished_good').prefetch_related('ingredients__item').all()
    serializer_class = FormulaSerializer
    
    def create(self, request, *args, **kwargs):
        """Create formula with ingredients"""
        data = request.data.copy()
        ingredients_data = data.pop('ingredients', [])
        
        # Create the formula
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        formula = serializer.save()
        
        # Create formula items
        from .models import FormulaItem
        for ingredient_data in ingredients_data:
            FormulaItem.objects.create(
                formula=formula,
                item_id=ingredient_data.get('item_id'),
                percentage=ingredient_data.get('percentage', 0),
                notes=ingredient_data.get('notes')
            )
        
        # Return the formula with ingredients
        serializer = self.get_serializer(formula)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """Update formula and its ingredients"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy()
        ingredients_data = data.pop('ingredients', None)
        
        # Update the formula
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        formula = serializer.save()
        
        # Update ingredients if provided
        if ingredients_data is not None:
            from .models import FormulaItem
            # Delete existing ingredients
            FormulaItem.objects.filter(formula=formula).delete()
            # Create new ingredients
            for ingredient_data in ingredients_data:
                FormulaItem.objects.create(
                    formula=formula,
                    item_id=ingredient_data.get('item_id'),
                    percentage=ingredient_data.get('percentage', 0),
                    notes=ingredient_data.get('notes')
                )
        
        # Return the formula with ingredients
        serializer = self.get_serializer(formula)
        return Response(serializer.data)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.prefetch_related('items__item').all()
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.prefetch_related('items__item').all()
        
        # Filter by status if provided
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            import traceback
            print(f"Error in PurchaseOrderViewSet.list: {e}")
            traceback.print_exc()
            raise
    
    def create(self, request, *args, **kwargs):
        # Make a mutable copy of request.data
        data = request.data.copy()
        items_data = data.pop('items', [])
        
        # Handle vendor_id -> vendor_customer_name mapping
        if 'vendor_id' in data:
            vendor_id = data.pop('vendor_id')
            try:
                vendor = Vendor.objects.get(id=vendor_id)
                data['vendor_customer_name'] = vendor.name
                data['vendor_customer_id'] = str(vendor.id)
            except Vendor.DoesNotExist:
                return Response(
                    {'error': f'Vendor with id {vendor_id} not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Generate PO number if not provided (format: 2yy0000)
        if not data.get('po_number'):
            data['po_number'] = generate_po_number()
        
        # Ensure po_type is set
        if 'po_type' not in data:
            data['po_type'] = 'vendor'
        
        # Set required_date from expected_delivery_date if not provided
        if not data.get('required_date') and data.get('expected_delivery_date'):
            data['required_date'] = data['expected_delivery_date']
        
        # Set expected_delivery_date to match required_date if not provided
        if not data.get('expected_delivery_date') and data.get('required_date'):
            data['expected_delivery_date'] = data['required_date']
        
        # Create the purchase order
        try:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            purchase_order = serializer.save()
        except Exception as e:
            import traceback
            print(f"Error creating PurchaseOrder: {e}")
            traceback.print_exc()
            return Response(
                {'error': f'Failed to create purchase order: {str(e)}', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create purchase order items
        for item_data in items_data:
            try:
                item_id = item_data.get('item_id')
                if not item_id:
                    raise ValueError(f'item_id is required for item: {item_data}')
                
                # Map unit_cost to unit_price (database has unit_price, not unit_cost)
                unit_price = item_data.get('unit_cost', item_data.get('unit_price', 0))
                quantity_ordered = item_data.get('quantity', item_data.get('quantity_ordered', 0))
                
                if quantity_ordered <= 0:
                    raise ValueError(f'quantity must be greater than 0, got: {quantity_ordered}')
                
                PurchaseOrderItem.objects.create(
                    purchase_order=purchase_order,
                    item_id=item_id,
                    quantity_ordered=quantity_ordered,
                    unit_price=unit_price,  # Use unit_price as that's what exists in DB
                    notes=item_data.get('notes', ''),
                )
            except Exception as e:
                import traceback
                print(f"Error creating PurchaseOrderItem: {e}")
                print(f"Item data: {item_data}")
                traceback.print_exc()
                # Delete the purchase order if item creation fails
                purchase_order.delete()
                return Response(
                    {'error': f'Failed to create purchase order item: {str(e)}', 'item_data': item_data},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Calculate totals if method exists
        if hasattr(purchase_order, 'calculate_totals'):
            purchase_order.calculate_totals()
            purchase_order.save()
        
        # Return the created purchase order with items
        response_serializer = self.get_serializer(purchase_order)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True, methods=['post'])
    def issue(self, request, pk=None):
        """Issue a purchase order - changes status to 'issued' and updates inventory"""
        purchase_order = self.get_object()
        
        if purchase_order.status != 'draft':
            return Response(
                {'error': f'Purchase order must be in draft status to issue. Current status: {purchase_order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status to issued
        purchase_order.status = 'issued'
        purchase_order.save()
        
        # Increment on_order for each item
        for po_item in purchase_order.items.all():
            if po_item.item:
                item = po_item.item
                item.on_order = (item.on_order or 0) + po_item.quantity_ordered
                item.save()
        
        # Return updated purchase order
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Mark purchase order as received"""
        purchase_order = self.get_object()
        
        if purchase_order.status != 'issued':
            return Response(
                {'error': f'Purchase order must be in issued status to receive. Current status: {purchase_order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase_order.status = 'received'
        purchase_order.received_date = timezone.now()
        purchase_order.save()
        
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def revise(self, request, pk=None):
        """Create a revision of a purchase order"""
        original_po = self.get_object()
        
        # Create a copy of the PO
        new_po_data = {
            'po_number': original_po.po_number,  # Same PO number
            'po_type': original_po.po_type,
            'vendor_customer_name': original_po.vendor_customer_name,
            'vendor_customer_id': original_po.vendor_customer_id,
            'status': 'draft',  # New revision starts as draft
            'revision_number': (original_po.revision_number or 0) + 1,
            'original_po': original_po,
            'order_number': original_po.order_number,
            'expected_delivery_date': original_po.expected_delivery_date,
            'required_date': original_po.required_date,
            'shipping_terms': original_po.shipping_terms,
            'shipping_method': original_po.shipping_method,
            'ship_to_name': original_po.ship_to_name,
            'ship_to_address': original_po.ship_to_address,
            'ship_to_city': original_po.ship_to_city,
            'ship_to_state': original_po.ship_to_state,
            'ship_to_zip': original_po.ship_to_zip,
            'ship_to_country': original_po.ship_to_country,
            'vendor_address': original_po.vendor_address,
            'vendor_city': original_po.vendor_city,
            'vendor_state': original_po.vendor_state,
            'vendor_zip': original_po.vendor_zip,
            'vendor_country': original_po.vendor_country,
            'subtotal': original_po.subtotal,
            'discount': original_po.discount,
            'shipping_cost': original_po.shipping_cost,
            'total': original_po.total,
            'coa_sds_email': original_po.coa_sds_email,
            'notes': original_po.notes,
        }
        
        new_po = PurchaseOrder.objects.create(**new_po_data)
        
        # Copy items
        for original_item in original_po.items.all():
            PurchaseOrderItem.objects.create(
                purchase_order=new_po,
                item=original_item.item,
                quantity_ordered=original_item.quantity_ordered,
                unit_price=original_item.unit_price,
                notes=original_item.notes,
            )
        
        # If original PO was issued, reverse its inventory impact and mark as superseded
        if original_po.status == 'issued':
            # Reverse on_order for each item
            for po_item in original_po.items.all():
                if po_item.item:
                    item = po_item.item
                    item.on_order = max(0, (item.on_order or 0) - po_item.quantity_ordered)
                    item.save()
            
            original_po.status = 'superseded'
            original_po.save()
        
        serializer = self.get_serializer(new_po)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a purchase order"""
        purchase_order = self.get_object()
        
        if purchase_order.status == 'completed':
            return Response(
                {'error': 'Cannot cancel a completed purchase order'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If PO was issued, reverse inventory impact
        if purchase_order.status == 'issued':
            for po_item in purchase_order.items.all():
                if po_item.item:
                    item = po_item.item
                    item.on_order = max(0, (item.on_order or 0) - po_item.quantity_ordered)
                    item.save()
        
        purchase_order.status = 'cancelled'
        purchase_order.save()
        
        serializer = self.get_serializer(purchase_order)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.prefetch_related('items__item').all()
    serializer_class = SalesOrderSerializer
    
    def create(self, request, *args, **kwargs):
        # Make a mutable copy of request.data
        data = request.data.copy()
        items_data = data.pop('items', [])
        
        # Generate sales order number if not provided (format: 3yy0000)
        if not data.get('so_number'):
            data['so_number'] = generate_sales_order_number()
        
        # Handle customer - if customer or customer_id is provided, set customer FK
        customer_id = data.get('customer') or data.get('customer_id')
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
                data['customer'] = customer.id
                # Auto-populate customer_name if not provided
                if not data.get('customer_name'):
                    data['customer_name'] = customer.name
                if not data.get('customer_reference_number') and data.get('customer_id'):
                    data['customer_reference_number'] = data.get('customer_id')
            except Customer.DoesNotExist:
                pass
        
        # Handle ship_to_location - if ship_to_location is provided, validate it belongs to the customer
        ship_to_location_id = data.get('ship_to_location')
        if ship_to_location_id:
            try:
                from .models import ShipToLocation
                ship_to_location = ShipToLocation.objects.get(id=ship_to_location_id)
                # Validate that ship-to location belongs to the selected customer
                if customer_id and ship_to_location.customer.id != customer_id:
                    return Response(
                        {'error': 'Ship-to location does not belong to the selected customer'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Auto-populate address fields from ship-to location if not provided
                if not data.get('customer_address'):
                    data['customer_address'] = ship_to_location.address
                if not data.get('customer_city'):
                    data['customer_city'] = ship_to_location.city
                if not data.get('customer_state'):
                    data['customer_state'] = ship_to_location.state or ''
                if not data.get('customer_zip'):
                    data['customer_zip'] = ship_to_location.zip_code
                if not data.get('customer_country'):
                    data['customer_country'] = ship_to_location.country
                if not data.get('customer_phone'):
                    data['customer_phone'] = ship_to_location.phone or ''
            except ShipToLocation.DoesNotExist:
                return Response(
                    {'error': 'Ship-to location not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Create the sales order
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        sales_order = serializer.save()
        
        # Create sales order items with lot allocations
        for item_data in items_data:
            allocated_lots_data = item_data.pop('allocated_lots', [])
            so_item = SalesOrderItem.objects.create(
                sales_order=sales_order,
                **item_data
            )
            
            # Create lot allocations
            for lot_data in allocated_lots_data:
                SalesOrderLot.objects.create(
                    sales_order_item=so_item,
                    lot_id=lot_data.get('lot_id'),
                    quantity_allocated=lot_data.get('quantity_allocated', 0)
                )
                
                # Update quantity_allocated on the SO item
                so_item.quantity_allocated += lot_data.get('quantity_allocated', 0)
                so_item.save()
        
        # Return the created sales order with items
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def allocate(self, request, pk=None):
        """Allocate lots to sales order items. Creates distributed item lots if raw materials are checked in."""
        from django.db import transaction
        
        sales_order = self.get_object()
        items_data = request.data.get('items', [])
        
        with transaction.atomic():
            for item_data in items_data:
                item_id = item_data.get('item_id')
                is_distributed = item_data.get('is_distributed', False)
                allocations = item_data.get('allocations', [])
                raw_materials = item_data.get('raw_materials', [])
                
                try:
                    so_item = SalesOrderItem.objects.get(sales_order=sales_order, item_id=item_id)
                except SalesOrderItem.DoesNotExist:
                    return Response(
                        {'error': f'Sales order item for item {item_id} not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Delete existing allocations for this item
                SalesOrderLot.objects.filter(sales_order_item=so_item).delete()
                so_item.quantity_allocated = 0.0
                
                if is_distributed and raw_materials:
                    # For distributed items, create new lot from raw materials
                    # Only if raw materials are checked into inventory (have lots with status='accepted')
                    distributed_item = so_item.item
                    total_quantity = 0.0
                    raw_material_lots = []
                    
                    for rm_data in raw_materials:
                        lot_id = rm_data.get('lot_id')
                        quantity = float(rm_data.get('quantity', 0))
                        
                        try:
                            lot = Lot.objects.get(id=lot_id, status='accepted')
                            if lot.quantity_remaining < quantity:
                                return Response(
                                    {'error': f'Insufficient quantity in lot {lot.lot_number}. Available: {lot.quantity_remaining}, Requested: {quantity}'},
                                    status=status.HTTP_400_BAD_REQUEST
                                )
                            raw_material_lots.append((lot, quantity))
                            total_quantity += quantity
                        except Lot.DoesNotExist:
                            return Response(
                                {'error': f'Lot {lot_id} not found or not accepted'},
                                status=status.HTTP_404_NOT_FOUND
                            )
                    
                    # Create new lot for distributed item
                    new_lot_number = generate_lot_number()
                    new_lot = Lot.objects.create(
                        lot_number=new_lot_number,
                        item=distributed_item,
                        quantity=total_quantity,
                        quantity_remaining=total_quantity,
                        received_date=timezone.now(),
                        status='accepted'
                    )
                    
                    # Reduce raw material lot quantities and create transactions
                    for raw_lot, qty in raw_material_lots:
                        raw_lot.quantity_remaining -= qty
                        raw_lot.save()
                        
                        InventoryTransaction.objects.create(
                            transaction_type='production',
                            lot=raw_lot,
                            quantity=-qty,
                            reference_number=sales_order.so_number,
                            notes=f'Allocated to distributed item lot {new_lot_number}'
                        )
                    
                    # Create transaction for new lot
                    InventoryTransaction.objects.create(
                        transaction_type='production',
                        lot=new_lot,
                        quantity=total_quantity,
                        reference_number=sales_order.so_number,
                        notes=f'Created from raw materials for sales order {sales_order.so_number}'
                    )
                    
                    # Allocate the new lot to sales order
                    SalesOrderLot.objects.create(
                        sales_order_item=so_item,
                        lot=new_lot,
                        quantity_allocated=total_quantity
                    )
                    so_item.quantity_allocated = total_quantity
                    
                else:
                    # Regular items - allocate from existing lots
                    for allocation in allocations:
                        lot_id = allocation.get('lot_id')
                        quantity = float(allocation.get('quantity', 0))
                        
                        try:
                            lot = Lot.objects.get(id=lot_id, item_id=item_id, status='accepted')
                            if lot.quantity_remaining < quantity:
                                return Response(
                                    {'error': f'Insufficient quantity in lot {lot.lot_number}. Available: {lot.quantity_remaining}, Requested: {quantity}'},
                                    status=status.HTTP_400_BAD_REQUEST
                                )
                            
                            SalesOrderLot.objects.create(
                                sales_order_item=so_item,
                                lot=lot,
                                quantity_allocated=quantity
                            )
                            so_item.quantity_allocated += quantity
                        except Lot.DoesNotExist:
                            return Response(
                                {'error': f'Lot {lot_id} not found for item {item_id}'},
                                status=status.HTTP_404_NOT_FOUND
                            )
                
                so_item.save()
            
            # Update sales order status to 'allocated' if any allocations exist
            total_allocated = sum(item.quantity_allocated for item in sales_order.items.all())
            if total_allocated > 0:
                sales_order.status = 'allocated'
                sales_order.save()
        
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        """Ship the sales order and create invoice."""
        from django.db import transaction
        from datetime import datetime, timedelta
        import re
        
        sales_order = self.get_object()
        ship_date_str = request.data.get('ship_date')
        invoice_date_str = request.data.get('invoice_date', ship_date_str)
        
        if not ship_date_str:
            return Response(
                {'error': 'ship_date is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            ship_date = datetime.strptime(ship_date_str, '%Y-%m-%d').date()
            invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else ship_date
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate all items are fully allocated
        for item in sales_order.items.all():
            if item.quantity_allocated < item.quantity_ordered:
                return Response(
                    {'error': f'Item {item.item.name} is not fully allocated. Allocated: {item.quantity_allocated}, Ordered: {item.quantity_ordered}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        with transaction.atomic():
            # Reduce lot quantities and create inventory transactions
            for so_item in sales_order.items.all():
                for allocation in SalesOrderLot.objects.filter(sales_order_item=so_item):
                    lot = allocation.lot
                    quantity = allocation.quantity_allocated
                    
                    if lot.quantity_remaining < quantity:
                        return Response(
                            {'error': f'Insufficient quantity in lot {lot.lot_number}. Available: {lot.quantity_remaining}, Required: {quantity}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    lot.quantity_remaining -= quantity
                    lot.save()
                    
                    InventoryTransaction.objects.create(
                        transaction_type='adjustment',
                        lot=lot,
                        quantity=-quantity,
                        reference_number=sales_order.so_number,
                        notes=f'Shipped for sales order {sales_order.so_number}'
                    )
                    
                    so_item.quantity_shipped += quantity
                    so_item.save()
            
            # Update sales order
            sales_order.actual_ship_date = timezone.make_aware(datetime.combine(ship_date, datetime.min.time()))
            sales_order.status = 'shipped'
            sales_order.save()
            
            # Create invoice
            invoice_number = generate_invoice_number()
            
            # Calculate due date from payment terms
            due_date = invoice_date
            if sales_order.customer and sales_order.customer.payment_terms:
                payment_terms = sales_order.customer.payment_terms
                # Parse payment terms (e.g., "Net 30" -> 30 days)
                match = re.search(r'(\d+)', payment_terms)
                if match:
                    days = int(match.group(1))
                    due_date = invoice_date + timedelta(days=days)
            
            # Calculate totals from sales order
            subtotal = sum(item.unit_price * item.quantity_ordered for item in sales_order.items.all() if item.unit_price)
            # Get freight, discount, tax from sales order if available, otherwise 0
            freight = getattr(sales_order, 'freight', 0.0) or 0.0
            discount = getattr(sales_order, 'discount', 0.0) or 0.0
            tax = 0.0  # Calculate tax if needed
            grand_total = subtotal + freight + tax - discount
            
            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                sales_order=sales_order,
                invoice_date=invoice_date,
                due_date=due_date,
                status='draft',
                subtotal=subtotal,
                freight=freight,
                tax=tax,
                discount=discount,
                grand_total=grand_total,
                notes=f'Created from sales order {sales_order.so_number}'
            )
            
            # Create invoice items
            for so_item in sales_order.items.all():
                InvoiceItem.objects.create(
                    invoice=invoice,
                    sales_order_item=so_item,
                    description=so_item.item.name,
                    quantity=so_item.quantity_shipped,
                    unit_price=so_item.unit_price or 0.0,
                    total=(so_item.unit_price or 0.0) * so_item.quantity_shipped
                )
        
        invoice_serializer = InvoiceSerializer(invoice)
        serializer = self.get_serializer(sales_order)
        
        return Response({
            'sales_order': serializer.data,
            'invoice': invoice_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel sales order and clean up allocations. Deletes distributed item lots permanently."""
        from django.db import transaction
        
        sales_order = self.get_object()
        
        with transaction.atomic():
            # Find all allocations
            for so_item in sales_order.items.all():
                allocations = SalesOrderLot.objects.filter(sales_order_item=so_item)
                
                for allocation in allocations:
                    lot = allocation.lot
                    
                    # Check if this is a distributed item lot (created for this sales order)
                    # We can identify this by checking if the lot was created recently and
                    # has a transaction referencing this sales order
                    is_distributed_lot = InventoryTransaction.objects.filter(
                        lot=lot,
                        reference_number=sales_order.so_number,
                        notes__icontains='distributed'
                    ).exists()
                    
                    if is_distributed_lot:
                        # This is a distributed item lot - delete it and reverse raw materials
                        # Find the raw material transactions
                        raw_material_transactions = InventoryTransaction.objects.filter(
                            reference_number=sales_order.so_number,
                            quantity__lt=0,  # Negative quantities are raw materials
                            notes__icontains=lot.lot_number
                        )
                        
                        # Reverse raw material quantities
                        for trans in raw_material_transactions:
                            raw_lot = trans.lot
                            raw_lot.quantity_remaining += abs(trans.quantity)
                            raw_lot.save()
                            
                            # Create reverse transaction
                            InventoryTransaction.objects.create(
                                transaction_type='adjustment',
                                lot=raw_lot,
                                quantity=abs(trans.quantity),
                                reference_number=sales_order.so_number,
                                notes=f'Reversed allocation from cancelled order {sales_order.so_number}'
                            )
                        
                        # Delete the distributed lot
                        lot.delete()
                
                # Delete all allocations
                allocations.delete()
                so_item.quantity_allocated = 0.0
                so_item.save()
            
            # Cancel any invoices
            Invoice.objects.filter(sales_order=sales_order).update(status='cancelled')
            
            # Update sales order status
            sales_order.status = 'cancelled'
            sales_order.save()
        
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related('sales_order', 'sales_order__customer').prefetch_related('items').all()
    serializer_class = InvoiceSerializer
    
    def get_queryset(self):
        queryset = Invoice.objects.select_related('sales_order', 'sales_order__customer').prefetch_related('items').all()
        status_filter = self.request.query_params.get('status', None)
        customer_id = self.request.query_params.get('customer_id', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if customer_id:
            queryset = queryset.filter(sales_order__customer_id=customer_id)
        if start_date:
            queryset = queryset.filter(invoice_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(invoice_date__lte=end_date)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def aging_report(self, request):
        """Get aging report grouped by aging buckets"""
        invoices = self.get_queryset().exclude(status='paid')
        
        aging_buckets = {
            'current': [],  # Not yet due
            '0_30': [],     # 0-30 days overdue
            '31_60': [],    # 31-60 days overdue
            '61_90': [],    # 61-90 days overdue
            '90_plus': []   # 90+ days overdue
        }
        
        for invoice in invoices:
            days = invoice.days_aging
            if days < 0:
                aging_buckets['current'].append(invoice)
            elif days <= 30:
                aging_buckets['0_30'].append(invoice)
            elif days <= 60:
                aging_buckets['31_60'].append(invoice)
            elif days <= 90:
                aging_buckets['61_90'].append(invoice)
            else:
                aging_buckets['90_plus'].append(invoice)
        
        # Calculate totals
        totals = {}
        for bucket, invs in aging_buckets.items():
            totals[bucket] = sum(inv.grand_total for inv in invs)
        
        serializer = self.get_serializer(list(aging_buckets.values())[0] + list(aging_buckets.values())[1] + 
                                        list(aging_buckets.values())[2] + list(aging_buckets.values())[3] + 
                                        list(aging_buckets.values())[4], many=True)
        
        return Response({
            'buckets': {
                'current': {'invoices': [self.get_serializer(inv).data for inv in aging_buckets['current']], 'total': totals['current']},
                '0_30': {'invoices': [self.get_serializer(inv).data for inv in aging_buckets['0_30']], 'total': totals['0_30']},
                '31_60': {'invoices': [self.get_serializer(inv).data for inv in aging_buckets['31_60']], 'total': totals['31_60']},
                '61_90': {'invoices': [self.get_serializer(inv).data for inv in aging_buckets['61_90']], 'total': totals['61_90']},
                '90_plus': {'invoices': [self.get_serializer(inv).data for inv in aging_buckets['90_plus']], 'total': totals['90_plus']},
            },
            'grand_total': sum(totals.values())
        })


class CalendarEventsViewSet(viewsets.ViewSet):
    """Calendar events for shipments, raw materials, and production"""
    
    @action(detail=False, methods=['get'])
    def events(self, request):
        from datetime import datetime, timedelta
        
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        event_types = request.query_params.get('event_types', 'shipments,raw_materials,production').split(',')
        
        # Parse dates
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        events = []
        
        # Shipment events
        if 'shipments' in event_types:
            shipments = SalesOrder.objects.filter(
                status__in=['allocated', 'shipped', 'completed']
            ).exclude(status='cancelled')
            
            if start_date:
                shipments = shipments.filter(
                    models.Q(actual_ship_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time()))) | 
                    models.Q(expected_ship_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time())))
                )
            if end_date:
                shipments = shipments.filter(
                    models.Q(actual_ship_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time()))) | 
                    models.Q(expected_ship_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time())))
                )
            
            for so in shipments:
                # Use actual_ship_date if available, otherwise expected_ship_date
                ship_date = so.actual_ship_date.date() if so.actual_ship_date else (so.expected_ship_date.date() if so.expected_ship_date else None)
                if ship_date:
                    events.append({
                        'id': f'shipment_{so.id}',
                        'type': 'shipment',
                        'title': f'Ship {so.so_number}',
                        'date': ship_date.isoformat(),
                        'sales_order_id': so.id,
                        'sales_order_number': so.so_number,
                        'customer_name': so.customer_name,
                        'is_actual': so.actual_ship_date is not None,
                    })
        
        # Raw material receipt events
        if 'raw_materials' in event_types:
            from .models import PurchaseOrder
            raw_materials = PurchaseOrder.objects.filter(
                status__in=['issued', 'received', 'completed']
            ).exclude(status='cancelled')
            
            if start_date:
                raw_materials = raw_materials.filter(
                    models.Q(expected_delivery_date__gte=start_date) if hasattr(PurchaseOrder, 'expected_delivery_date') else models.Q()
                )
            if end_date:
                raw_materials = raw_materials.filter(
                    models.Q(expected_delivery_date__lte=end_date) if hasattr(PurchaseOrder, 'expected_delivery_date') else models.Q()
                )
            
            # Also get from lots
            lots = Lot.objects.filter(status='accepted')
            if start_date:
                lots = lots.filter(received_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time())))
            if end_date:
                lots = lots.filter(received_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time())))
            
            for lot in lots:
                events.append({
                    'id': f'raw_material_{lot.id}',
                    'type': 'raw_material',
                    'title': f'Receipt: {lot.lot_number}',
                    'date': lot.received_date.date().isoformat(),
                    'lot_id': lot.id,
                    'lot_number': lot.lot_number,
                    'item_name': lot.item.name,
                    'po_number': lot.po_number,
                })
        
        # Production events
        if 'production' in event_types:
            batches = ProductionBatch.objects.all()
            
            if start_date:
                batches = batches.filter(production_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time())))
            if end_date:
                batches = batches.filter(production_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time())))
            
            for batch in batches:
                events.append({
                    'id': f'production_{batch.id}',
                    'type': 'production',
                    'title': f'Batch {batch.batch_number}',
                    'date': batch.production_date.date().isoformat(),
                    'batch_id': batch.id,
                    'batch_number': batch.batch_number,
                    'status': batch.status,
                    'is_scheduled': batch.status == 'scheduled',
                })
        
        # Sort by date
        events.sort(key=lambda x: x['date'])
        
        return Response({'events': events})


class InventoryTransactionViewSet(viewsets.ModelViewSet):
    queryset = InventoryTransaction.objects.select_related('lot__item').all()
    serializer_class = InventoryTransactionSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.none()  # Default to empty queryset
    serializer_class = CustomerSerializer
    
    def get_queryset(self):
        from django.db import connection
        from django.db.utils import OperationalError
        
        try:
            # Check if table exists first
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
                table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Table doesn't exist - return empty queryset
                return Customer.objects.none()
            
            # Table exists - try to query
            queryset = Customer.objects.all()
            is_active = self.request.query_params.get('is_active', None)
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
            return queryset
        except OperationalError:
            # Database error - table likely doesn't exist
            return Customer.objects.none()
        except Exception as e:
            # Any other error
            import traceback
            print(f"Error in CustomerViewSet.get_queryset: {e}")
            traceback.print_exc()
            return Customer.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db.utils import OperationalError
        from django.db import connection
        
        try:
            # First check if table exists
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
                table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Table doesn't exist - return empty list
                return Response([])
            
            # Table exists - try to get queryset
            queryset = self.get_queryset()
            
            # Try to serialize
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
            
        except OperationalError as e:
            # Database error - table likely doesn't exist
            import traceback
            print(f"OperationalError in CustomerViewSet.list: {e}")
            traceback.print_exc()
            return Response([])
        except Exception as e:
            # Any other error, return empty list
            import traceback
            print(f"Error in CustomerViewSet.list: {e}")
            traceback.print_exc()
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        from django.db.utils import OperationalError
        
        # Check if table exists first
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
                table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Table doesn't exist - try to create it using raw SQL
                try:
                    self._create_customer_table()
                    # Also create other CRM tables
                    self._create_crm_tables()
                    # Verify table was created by checking again
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
                    if not cursor.fetchone():
                        return Response(
                            {'error': 'Failed to create customer table. Please run migrations.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return Response(
                        {'error': f'Failed to create customer table: {str(e)}. Please run migrations.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        except Exception as e:
            return Response(
                {'error': f'Database error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Make a mutable copy of request.data
        data = request.data.copy()
        
        # Auto-generate customer_id if not provided or empty
        if 'customer_id' not in data or not data.get('customer_id'):
            try:
                data['customer_id'] = generate_customer_id()
            except Exception as e:
                # Fallback: generate simple ID
                import traceback
                print(f"Error generating customer ID: {e}")
                traceback.print_exc()
                # Use timestamp-based ID as fallback
                from django.utils import timezone
                data['customer_id'] = f"{int(timezone.now().timestamp()) % 100000:05d}"
        
        # Create serializer with modified data
        try:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except OperationalError as e:
            return Response(
                {'error': f'Database error: {str(e)}. Please ensure migrations have been run.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Error creating customer: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _create_customer_table(self):
        """Create customer table if it doesn't exist (workaround for migration issues)"""
        from django.db import connection
        from django.utils import timezone
        
        with connection.cursor() as cursor:
            # Create Customer table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS erp_core_customer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id VARCHAR(100) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    contact_name VARCHAR(255),
                    email VARCHAR(254),
                    phone VARCHAR(50),
                    address TEXT,
                    city VARCHAR(100),
                    state VARCHAR(50),
                    zip_code VARCHAR(20),
                    country VARCHAR(100) DEFAULT 'USA',
                    payment_terms VARCHAR(50),
                    notes TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create index
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS erp_core_customer_customer_id ON erp_core_customer(customer_id)")
            except Exception:
                pass  # Index might already exist
            
            # Also create CustomerNumberSequence table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS erp_core_customernumbersequence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence_number INTEGER NOT NULL DEFAULT 0,
                    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert initial sequence record if it doesn't exist
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO erp_core_customernumbersequence (id, sequence_number, last_updated)
                    VALUES (1, 0, CURRENT_TIMESTAMP)
                """)
            except Exception:
                pass  # Record might already exist
    
    def _create_crm_tables(self):
        """Create all CRM-related tables if they don't exist"""
        from django.db import connection
        
        with connection.cursor() as cursor:
            # CustomerPricing table (if it doesn't exist - it might already exist)
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS erp_core_customerpricing (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        item_id INTEGER NOT NULL,
                        unit_price REAL NOT NULL,
                        unit_of_measure VARCHAR(10) NOT NULL DEFAULT 'lbs',
                        effective_date DATE NOT NULL,
                        expiry_date DATE,
                        is_active BOOLEAN DEFAULT 1,
                        notes TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(customer_id, item_id, effective_date)
                    )
                """)
            except Exception:
                pass
            
            # ShipToLocation table
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS erp_core_shiptolocation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        location_name VARCHAR(255) NOT NULL,
                        contact_name VARCHAR(255),
                        email VARCHAR(254),
                        phone VARCHAR(50),
                        address TEXT NOT NULL,
                        city VARCHAR(100) NOT NULL,
                        state VARCHAR(50),
                        zip_code VARCHAR(20) NOT NULL,
                        country VARCHAR(100) DEFAULT 'USA',
                        is_default BOOLEAN DEFAULT 0,
                        is_active BOOLEAN DEFAULT 1,
                        notes TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            except Exception:
                pass
            
            # CustomerContact table
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS erp_core_customercontact (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        first_name VARCHAR(100) NOT NULL,
                        last_name VARCHAR(100) NOT NULL,
                        title VARCHAR(100),
                        email VARCHAR(254),
                        phone VARCHAR(50),
                        mobile VARCHAR(50),
                        is_primary BOOLEAN DEFAULT 0,
                        is_active BOOLEAN DEFAULT 1,
                        notes TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            except Exception:
                pass
            
            # SalesCall table
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS erp_core_salescall (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        contact_id INTEGER,
                        call_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        call_type VARCHAR(20) NOT NULL DEFAULT 'phone',
                        subject VARCHAR(255),
                        notes TEXT NOT NULL,
                        follow_up_required BOOLEAN DEFAULT 0,
                        follow_up_date DATETIME,
                        created_by VARCHAR(255),
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            except Exception:
                pass
            
            # CustomerForecast table
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS erp_core_customerforecast (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_id INTEGER NOT NULL,
                        item_id INTEGER NOT NULL,
                        forecast_period VARCHAR(20) NOT NULL,
                        forecast_quantity REAL NOT NULL,
                        unit_of_measure VARCHAR(10) NOT NULL DEFAULT 'lbs',
                        notes TEXT,
                        created_by VARCHAR(255),
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(customer_id, item_id, forecast_period)
                    )
                """)
            except Exception:
                pass


class CustomerPricingViewSet(viewsets.ModelViewSet):
    queryset = CustomerPricing.objects.none()
    serializer_class = CustomerPricingSerializer
    
    def get_queryset(self):
        from django.db import connection
        from django.db.utils import OperationalError
        from django.utils import timezone
        from datetime import date
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerpricing'")
                if not cursor.fetchone():
                    return CustomerPricing.objects.none()
            
            queryset = CustomerPricing.objects.select_related('customer', 'item').all()
            customer_id = self.request.query_params.get('customer_id', None)
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            
            # Filter by is_active if provided
            is_active = self.request.query_params.get('is_active', None)
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')
            
            # Filter by effective_date and expiry_date to show only currently active pricing
            today = date.today()
            from django.db.models import Q
            queryset = queryset.filter(
                effective_date__lte=today,
                is_active=True
            ).filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
            )
            
            return queryset
        except Exception:
            return CustomerPricing.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerpricing'")
                if not cursor.fetchone():
                    # Try to create table
                    try:
                        CustomerViewSet()._create_crm_tables()
                    except Exception:
                        pass
                    return Response([])
            
            return super().list(request, *args, **kwargs)
        except Exception:
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        import logging
        logger = logging.getLogger(__name__)
        
        # Ensure table exists
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerpricing'")
                if not cursor.fetchone():
                    CustomerViewSet()._create_crm_tables()
        except Exception as e:
            logger.error(f"Error ensuring table exists: {e}")
        
        try:
            logger.info(f"Creating CustomerPricing with data: {request.data}")
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating CustomerPricing: {e}", exc_info=True)
            raise


class VendorPricingViewSet(viewsets.ModelViewSet):
    queryset = VendorPricing.objects.select_related('item').all()
    serializer_class = VendorPricingSerializer
    
    def get_queryset(self):
        queryset = VendorPricing.objects.select_related('item').all()
        vendor_name = self.request.query_params.get('vendor_name', None)
        if vendor_name:
            queryset = queryset.filter(vendor_name__icontains=vendor_name)
        item_id = self.request.query_params.get('item_id', None)
        if item_id:
            queryset = queryset.filter(item_id=item_id)
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset


class ShipToLocationViewSet(viewsets.ModelViewSet):
    queryset = ShipToLocation.objects.none()
    serializer_class = ShipToLocationSerializer
    
    def get_queryset(self):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_shiptolocation'")
                if not cursor.fetchone():
                    return ShipToLocation.objects.none()
            
            queryset = ShipToLocation.objects.select_related('customer').all()
            customer_id = self.request.query_params.get('customer_id', None)
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            return queryset
        except Exception:
            return ShipToLocation.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_shiptolocation'")
                if not cursor.fetchone():
                    try:
                        CustomerViewSet()._create_crm_tables()
                    except Exception:
                        pass
                    return Response([])
            
            return super().list(request, *args, **kwargs)
        except Exception:
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_shiptolocation'")
                if not cursor.fetchone():
                    CustomerViewSet()._create_crm_tables()
        except Exception:
            pass
        
        return super().create(request, *args, **kwargs)


class CustomerContactViewSet(viewsets.ModelViewSet):
    queryset = CustomerContact.objects.none()
    serializer_class = CustomerContactSerializer
    
    def get_queryset(self):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
                if not cursor.fetchone():
                    return CustomerContact.objects.none()
            
            queryset = CustomerContact.objects.select_related('customer').all()
            customer_id = self.request.query_params.get('customer_id', None)
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            return queryset
        except Exception:
            return CustomerContact.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
                if not cursor.fetchone():
                    try:
                        CustomerViewSet()._create_crm_tables()
                    except Exception:
                        pass
                    return Response([])
            
            return super().list(request, *args, **kwargs)
        except Exception:
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
                if not cursor.fetchone():
                    CustomerViewSet()._create_crm_tables()
        except Exception:
            pass
        
        return super().create(request, *args, **kwargs)


class SalesCallViewSet(viewsets.ModelViewSet):
    queryset = SalesCall.objects.none()
    serializer_class = SalesCallSerializer
    
    def get_queryset(self):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salescall'")
                if not cursor.fetchone():
                    return SalesCall.objects.none()
            
            queryset = SalesCall.objects.select_related('customer', 'contact').all()
            customer_id = self.request.query_params.get('customer_id', None)
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            return queryset
        except Exception:
            return SalesCall.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salescall'")
                if not cursor.fetchone():
                    try:
                        CustomerViewSet()._create_crm_tables()
                    except Exception:
                        pass
                    return Response([])
            
            return super().list(request, *args, **kwargs)
        except Exception:
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salescall'")
                if not cursor.fetchone():
                    CustomerViewSet()._create_crm_tables()
        except Exception:
            pass
        
        return super().create(request, *args, **kwargs)


class CustomerForecastViewSet(viewsets.ModelViewSet):
    queryset = CustomerForecast.objects.none()
    serializer_class = CustomerForecastSerializer
    
    def get_queryset(self):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerforecast'")
                if not cursor.fetchone():
                    return CustomerForecast.objects.none()
            
            queryset = CustomerForecast.objects.select_related('customer', 'item').all()
            customer_id = self.request.query_params.get('customer_id', None)
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            return queryset
        except Exception:
            return CustomerForecast.objects.none()
    
    def list(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerforecast'")
                if not cursor.fetchone():
                    try:
                        CustomerViewSet()._create_crm_tables()
                    except Exception:
                        pass
                    return Response([])
            
            return super().list(request, *args, **kwargs)
        except Exception:
            return Response([])
    
    def create(self, request, *args, **kwargs):
        from django.db import connection
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerforecast'")
                if not cursor.fetchone():
                    CustomerViewSet()._create_crm_tables()
        except Exception:
            pass
        
        return super().create(request, *args, **kwargs)


class CustomerUsageViewSet(viewsets.ViewSet):
    """ViewSet for customer usage/volume data"""
    
    def list(self, request):
        """Get usage data for a specific customer"""
        from django.db.models import Sum, Q
        from django.db import connection
        from django.db.utils import OperationalError
        from datetime import datetime
        
        customer_id = request.query_params.get('customer_id', None)
        item_id = request.query_params.get('item_id', None)
        year = request.query_params.get('year', None)
        
        if not customer_id:
            return Response({'error': 'customer_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check if Customer table exists
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
                if not cursor.fetchone():
                    return Response({
                        'customer_id': int(customer_id),
                        'customer_name': 'Unknown',
                        'usage': []
                    })
            
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)
        except OperationalError:
            return Response({
                'customer_id': int(customer_id),
                'customer_name': 'Unknown',
                'usage': []
            })
        
        # Check if SalesOrder table exists
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salesorder'")
                if not cursor.fetchone():
                    return Response({
                        'customer_id': customer.id,
                        'customer_name': customer.name,
                        'usage': []
                    })
                # Also check for SalesOrderItem table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salesorderitem'")
                if not cursor.fetchone():
                    return Response({
                        'customer_id': customer.id,
                        'customer_name': customer.name,
                        'usage': []
                    })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'usage': []
            })
        
        # Get all sales orders for this customer
        try:
            sales_orders = SalesOrder.objects.filter(customer=customer, status__in=['allocated', 'shipped'])
        except (OperationalError, Exception) as e:
            import traceback
            traceback.print_exc()
            return Response({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'usage': []
            })
        
        # Filter by year if provided
        if year:
            sales_orders = sales_orders.filter(order_date__year=year)
        
        # Get current year for YTD calculation
        current_year = datetime.now().year
        
        # Aggregate usage by item
        usage_data = {}
        
        try:
            for so in sales_orders:
                try:
                    for item in so.items.all():
                        try:
                            if item_id and item.item_id != int(item_id):
                                continue
                            
                            item_key = item.item_id
                            if item_key not in usage_data:
                                usage_data[item_key] = {
                                    'item_id': item.item_id,
                                    'item_sku': item.item.sku if item.item else None,
                                    'item_name': item.item.name if item.item else None,
                                    'total_quantity': 0.0,
                                    'ytd_quantity': 0.0,
                                    'order_count': 0,
                                    'ytd_order_count': 0,
                                }
                            
                            quantity = item.quantity or 0.0
                            usage_data[item_key]['total_quantity'] += quantity
                            usage_data[item_key]['order_count'] += 1
                            
                            # YTD calculation
                            if so.order_date.year == current_year:
                                usage_data[item_key]['ytd_quantity'] += quantity
                                usage_data[item_key]['ytd_order_count'] += 1
                        except Exception:
                            # Skip this item if there's an error
                            continue
                except Exception:
                    # Skip this sales order if there's an error accessing items
                    continue
        except Exception as e:
            # If there's any error in the aggregation, return empty usage
            import traceback
            traceback.print_exc()
            return Response({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'usage': []
            })
        
        try:
            return Response({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'usage': list(usage_data.values())
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'usage': []
            })
    
    @action(detail=False, methods=['get'], url_path='customer-usage')
    def customer_usage(self, request):
        """Get usage data for a specific customer (alias for list)"""
        return self.list(request)


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.prefetch_related('history', 'documents', 'exceptions').all()
    serializer_class = VendorSerializer
    
    @action(detail=True, methods=['post'])
    def history(self, request, pk=None):
        vendor = self.get_object()
        serializer = VendorHistorySerializer(data={
            **request.data,
            'vendor': vendor.id
        })
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        vendor = self.get_object()
        vendor.approval_status = 'approved'
        vendor.approved_date = timezone.now()
        vendor.approved_by = request.data.get('approved_by', 'DOOF')
        vendor.save()
        return Response(VendorSerializer(vendor).data)
    
    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        """Get approved items for this vendor with YTD usage"""
        vendor = self.get_object()
        from datetime import datetime
        from django.db.models import Sum
        
        # Get items for this vendor
        items = Item.objects.filter(vendor=vendor.name)
        
        # Calculate YTD usage from inventory transactions
        current_year = datetime.now().year
        items_data = []
        
        for item in items:
            # Get YTD usage from lots checked in this year
            ytd_usage = Lot.objects.filter(
                item=item,
                received_date__year=current_year
            ).aggregate(
                total=Sum('quantity')
            )['total'] or 0.0
            
            items_data.append({
                'id': item.id,
                'sku': item.sku,
                'name': item.name,
                'unit_of_measure': item.unit_of_measure,
                'pack_size': item.pack_size,
                'price': item.price,
                'ytd_usage': ytd_usage,
            })
        
        return Response(items_data)


class SupplierSurveyViewSet(viewsets.ModelViewSet):
    queryset = SupplierSurvey.objects.all()
    serializer_class = SupplierSurveySerializer
    
    def get_queryset(self):
        queryset = SupplierSurvey.objects.all()
        vendor_id = self.request.query_params.get('vendor', None)
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
        return queryset
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        survey = self.get_object()
        survey.status = 'under_review'
        survey.submitted_date = timezone.now()
        survey.save()
        return Response(SupplierSurveySerializer(survey).data)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        survey = self.get_object()
        survey.status = 'approved'
        survey.approved_date = timezone.now()
        survey.approved_by = request.data.get('approved_by', 'DOOF')
        survey.reviewer_notes = request.data.get('reviewer_notes', '')
        survey.save()
        return Response(SupplierSurveySerializer(survey).data)


class SupplierDocumentViewSet(viewsets.ModelViewSet):
    queryset = SupplierDocument.objects.all()
    serializer_class = SupplierDocumentSerializer
    
    def get_queryset(self):
        queryset = SupplierDocument.objects.all()
        vendor_id = self.request.query_params.get('vendor', None)
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
        return queryset


class TemporaryExceptionViewSet(viewsets.ModelViewSet):
    queryset = TemporaryException.objects.all()
    serializer_class = TemporaryExceptionSerializer


class CostMasterViewSet(viewsets.ModelViewSet):
    queryset = CostMaster.objects.all()
    serializer_class = CostMasterSerializer
    
    def get_queryset(self):
        queryset = CostMaster.objects.all()
        product_code = self.request.query_params.get('product_code', None)
        vendor = self.request.query_params.get('vendor', None)
        if product_code:
            queryset = queryset.filter(wwi_product_code=product_code)
        if vendor:
            queryset = queryset.filter(vendor=vendor)
        return queryset
    
    @action(detail=False, methods=['get'])
    def pricing_history(self, request):
        """Get pricing history for multiple items by product codes"""
        from .serializers import CostMasterHistorySerializer
        product_codes = request.query_params.getlist('product_code')
        
        if not product_codes:
            return Response(
                {'error': 'product_code parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get CostMaster entries for these product codes
        cost_masters = CostMaster.objects.filter(wwi_product_code__in=product_codes)
        
        # Get all history records for these cost masters
        history = CostMasterHistory.objects.filter(
            cost_master__in=cost_masters
        ).select_related('cost_master').order_by('cost_master__wwi_product_code', '-effective_date')
        
        serializer = CostMasterHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get pricing history for a specific CostMaster item"""
        from .serializers import CostMasterHistorySerializer
        cost_master = self.get_object()
        history = CostMasterHistory.objects.filter(cost_master=cost_master).order_by('-effective_date')
        serializer = CostMasterHistorySerializer(history, many=True)
        return Response(serializer.data)


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer


class FinishedProductSpecificationViewSet(viewsets.ModelViewSet):
    queryset = FinishedProductSpecification.objects.select_related('item').all()
    serializer_class = FinishedProductSpecificationSerializer
    
    def get_queryset(self):
        queryset = FinishedProductSpecification.objects.select_related('item').all()
        item_id = self.request.query_params.get('item', None)
        if item_id:
            queryset = queryset.filter(item_id=item_id)
        return queryset
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def create(self, request, *args, **kwargs):
        """Create FPS and automatically generate PDF"""
        # The serializer will handle item_id -> item mapping via PrimaryKeyRelatedField
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fps = serializer.save()
        
        # Automatically generate PDF
        try:
            self._generate_and_save_pdf(fps)
        except Exception as e:
            import traceback
            print(f"Error generating PDF: {e}")
            traceback.print_exc()
            # Continue even if PDF generation fails
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def update(self, request, *args, **kwargs):
        """Update FPS and regenerate PDF if needed"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        fps = serializer.save()
        
        # Regenerate PDF on update
        try:
            self._generate_and_save_pdf(fps)
        except Exception as e:
            import traceback
            print(f"Error regenerating PDF: {e}")
            traceback.print_exc()
        
        return Response(serializer.data)
    
    def _generate_and_save_pdf(self, fps):
        """Internal method to generate and save PDF using Word template"""
        import os
        import tempfile
        import re
        from pathlib import Path
        from docx import Document
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.conf import settings
        from .models import Formula
        
        item = fps.item
        
        # Get template path - template should be in the project root (one level up from backend_django)
        PROJECT_ROOT = Path(settings.BASE_DIR).parent.parent
        template_path = PROJECT_ROOT / 'Finished Product Specification Form (3.3-01).docx'
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found at {template_path}")
        
        # Load template
        doc = Document(str(template_path))
        
        # Get formula if exists
        formula_text = ''
        try:
            formula = Formula.objects.get(finished_good=item)
            formula_text = f"Version: {formula.version}\n\n"
            for ingredient in formula.ingredients.all():
                formula_text += f"{ingredient.item.name}: {ingredient.percentage}%\n"
        except Formula.DoesNotExist:
            formula_text = 'No formula assigned'
        
        # Define replacement mappings - these should match text patterns in the template
        replacements = {
            'Product Name': item.name,
            'Item number': item.sku,
            'Product Description': fps.product_description or '',
            'Color Specification': fps.color_specification or '',
            'pH': fps.ph or '',
            'Water Activity': fps.water_activity or '',
            'Microbiological Requirements': fps.microbiological_requirements or '',
            'Shelf life / Storage Requirements': fps.shelf_life_storage or '',
            'Type of Packaging': fps.packaging_type or '',
            'Additional Criteria': fps.additional_criteria or '',
            'Processing Requirements': fps.processing_requirements or '',
            'Product Formula': formula_text,
            'Name and Title of Person Completing Form': fps.completed_by_name or '',
            'Signature and Date': f"{fps.completed_by_signature or ''} {str(fps.completed_date) if fps.completed_date else ''}",
            'Test frequency': fps.test_frequency or '',
        }
        
        # Function to replace text in a paragraph (handles Word's internal structure)
        def replace_in_paragraph(paragraph, old_text, new_text):
            """Replace text in a paragraph, handling Word's run structure"""
            if old_text in paragraph.text:
                # Clear existing runs
                paragraph.clear()
                # Add new text
                run = paragraph.add_run(new_text)
                return True
            return False
        
        # Replace text in all paragraphs
        for paragraph in doc.paragraphs:
            full_text = paragraph.text
            for key, value in replacements.items():
                # Look for patterns like "Product Name:" or "Product Name" followed by empty space
                patterns = [
                    rf'{re.escape(key)}\s*:\s*\n',
                    rf'{re.escape(key)}\s*\n',
                    rf'{re.escape(key)}\s*$',
                ]
                for pattern in patterns:
                    if re.search(pattern, full_text, re.IGNORECASE):
                        # Find the position and replace
                        match = re.search(pattern, full_text, re.IGNORECASE)
                        if match:
                            # Replace the entire paragraph with the new content
                            new_text = full_text[:match.start()] + f'{key}: {value}'
                            paragraph.clear()
                            paragraph.add_run(new_text)
                            break
        
        # Handle checkboxes - look for checklist items and mark them
        checklist_items = {
            'MSDS Created': fps.msds_created,
            'Commercial Spec Created': fps.commercial_spec_created,
            'Label Template Created': fps.label_template_created,
            'Product evaluated for micro growth': fps.micro_growth_evaluated,
            'Product Added to Kosher Letter': fps.kosher_letter_added,
            'Initial HACCP Plan Created': fps.haccp_plan_created,
        }
        
        for paragraph in doc.paragraphs:
            full_text = paragraph.text
            for item_text, checked in checklist_items.items():
                if item_text in full_text:
                    # Replace checkbox symbols
                    checkmark = '☑' if checked else '☐'
                    new_text = re.sub(r'[☐☑]', checkmark, full_text, count=1)
                    if new_text != full_text:
                        paragraph.clear()
                        paragraph.add_run(new_text)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
            doc.save(tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Convert DOCX to PDF using docx2pdf (requires Word or LibreOffice)
            try:
                from docx2pdf import convert
                pdf_path = tmp_path.replace('.docx', '.pdf')
                convert(tmp_path, pdf_path)
                
                # Read PDF content
                with open(pdf_path, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()
                
                # Clean up temp PDF file
                os.unlink(pdf_path)
            except Exception as e:
                # If conversion fails, fall back to using the DOCX file
                print(f"PDF conversion failed: {e}. Using DOCX file instead.")
                with open(tmp_path, 'rb') as docx_file:
                    pdf_content = docx_file.read()
            
            # Save PDF to model
            filename = f"FPS_{item.sku}_{item.name.replace(' ', '_').replace('/', '_')}.pdf"
            fps.fps_pdf.save(filename, ContentFile(pdf_content), save=True)
        finally:
            # Clean up temp DOCX file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        field_label_style = ParagraphStyle(
            'FieldLabel',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#000000'),
            fontName='Helvetica-Bold',
            spaceAfter=4
        )
        
        field_value_style = ParagraphStyle(
            'FieldValue',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12
        )
        
        # Header
        header_data = [
            ['6431 Michels Drive', ''],
            ['Washington, MO 63090', ''],
            ['314-835-8207', '']
        ]
        header_table = Table(header_data, colWidths=[4*inch, 4*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Title
        story.append(Paragraph('Finished Product Specification', title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Test frequency
        if fps.test_frequency:
            story.append(Paragraph(f'<b>Test frequency:</b> {fps.test_frequency}', field_value_style))
            story.append(Spacer(1, 0.1*inch))
        
        # Main specification fields
        spec_fields = [
            ('Product Name', item.name),
            ('Item number', item.sku),
            ('Product Description<br/>(physical state, color, odor, etc.)', fps.product_description or ''),
            ('Color Specification<br/>(CV, dye %, color strength, etc.)', fps.color_specification or ''),
            ('pH', fps.ph or ''),
            ('Water Activity (aW)', fps.water_activity or ''),
            ('Microbiological Requirements<br/>(if micro testing not required, rationale must be provided)', fps.microbiological_requirements or ''),
            ('Shelf life / Storage Requirements<br/>(temperature data)<br/>Include Basis for decision and record Shelf-Life Assignment Form (Document No. 5.1.4–03)<br/>Shelf-Life Study Log (Document No. 5.1.4–02)', fps.shelf_life_storage or ''),
            ('Type of Packaging', fps.packaging_type or ''),
            ('Additional Criteria<br/>(physical parameter testing, flavor profile, customer considerations, etc.)', fps.additional_criteria or ''),
        ]
        
        for label, value in spec_fields:
            story.append(Paragraph(f'<b>{label}</b>', field_label_style))
            story.append(Paragraph(value or '', field_value_style))
        
        # Footer note
        story.append(Spacer(1, 0.2*inch))
        footer_note = 'This document contains confidential and proprietary information intended solely for the recipient. By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, distribute, or use any information herein for purposes other than those expressly authorized. Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, please notify the sender immediately and delete this document from your system Finished Product Specification Form – Updated 12/10/2025 (GDM) – Reviewed by GDM – Effective Date 12/10/2025 – Doc No. 3.3 - 01.'
        story.append(Paragraph(footer_note, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#666666'))))
        
        story.append(PageBreak())
        
        # Checklist page
        story.append(header_table)
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('FINISHED PRODUCT SPECIFICATION CHECKLIST', title_style))
        story.append(Spacer(1, 0.3*inch))
        
        story.append(Paragraph(f'<b>Product Name:</b> {item.name}', field_value_style))
        story.append(Spacer(1, 0.2*inch))
        
        checklist_items = [
            ('MSDS Created', fps.msds_created),
            ('Commercial Spec Created / COA', fps.commercial_spec_created),
            ('Label Template Created', fps.label_template_created),
            ('Product evaluated for micro growth', fps.micro_growth_evaluated),
            ('Product Added to Kosher Letter', fps.kosher_letter_added),
            ('Initial HACCP Plan Created', fps.haccp_plan_created),
        ]
        
        for label, checked in checklist_items:
            checkmark = '✓' if checked else '☐'
            story.append(Paragraph(f'{checkmark} {label}', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('<b>Processing Requirements</b><br/>(i.e. specific tank or mixer, how long should product be mixed, allergen considerations, temperature requirements)', field_label_style))
        story.append(Paragraph(fps.processing_requirements or '', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('<b>Product Formula</b>', field_label_style))
        # Get formula if exists
        try:
            formula = Formula.objects.get(finished_good=item)
            formula_text = f"Version: {formula.version}\n\n"
            for ingredient in formula.ingredients.all():
                formula_text += f"{ingredient.item.name}: {ingredient.percentage}%\n"
            story.append(Paragraph(formula_text.replace('\n', '<br/>'), field_value_style))
        except Formula.DoesNotExist:
            story.append(Paragraph('No formula assigned', field_value_style))
        
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f'<b>Name and Title of Person Completing Form:</b><br/>{fps.completed_by_name or ""}', field_value_style))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f'<b>Signature and Date:</b><br/>{fps.completed_by_signature or ""} {fps.completed_date or ""}', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(footer_note, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#666666'))))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Save PDF to file
        filename = f"FPS_{item.sku}_{item.name.replace(' ', '_').replace('/', '_')}.pdf"
        fps.fps_pdf.save(filename, ContentFile(pdf_content), save=True)
    
    @action(detail=True, methods=['get'])
    def generate_pdf(self, request, pk=None):
        """Generate FPS PDF for a finished product specification"""
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from io import BytesIO
        from django.http import HttpResponse
        import os
        
        fps = self.get_object()
        item = fps.item
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#000000'),
            alignment=TA_LEFT
        )
        
        field_label_style = ParagraphStyle(
            'FieldLabel',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#000000'),
            fontName='Helvetica-Bold',
            spaceAfter=4
        )
        
        field_value_style = ParagraphStyle(
            'FieldValue',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12
        )
        
        # Header
        header_data = [
            ['6431 Michels Drive', ''],
            ['Washington, MO 63090', ''],
            ['314-835-8207', '']
        ]
        header_table = Table(header_data, colWidths=[4*inch, 4*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Title
        story.append(Paragraph('Finished Product Specification', title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Test frequency
        if fps.test_frequency:
            story.append(Paragraph(f'<b>Test frequency:</b> {fps.test_frequency}', field_value_style))
            story.append(Spacer(1, 0.1*inch))
        
        # Main specification fields
        spec_fields = [
            ('Product Name', item.name),
            ('Item number', item.sku),
            ('Product Description<br/>(physical state, color, odor, etc.)', fps.product_description or ''),
            ('Color Specification<br/>(CV, dye %, color strength, etc.)', fps.color_specification or ''),
            ('pH', fps.ph or ''),
            ('Water Activity (aW)', fps.water_activity or ''),
            ('Microbiological Requirements<br/>(if micro testing not required, rationale must be provided)', fps.microbiological_requirements or ''),
            ('Shelf life / Storage Requirements<br/>(temperature data)<br/>Include Basis for decision and record Shelf-Life Assignment Form (Document No. 5.1.4–03)<br/>Shelf-Life Study Log (Document No. 5.1.4–02)', fps.shelf_life_storage or ''),
            ('Type of Packaging', fps.packaging_type or ''),
            ('Additional Criteria<br/>(physical parameter testing, flavor profile, customer considerations, etc.)', fps.additional_criteria or ''),
        ]
        
        for label, value in spec_fields:
            story.append(Paragraph(f'<b>{label}</b>', field_label_style))
            story.append(Paragraph(value or '', field_value_style))
        
        # Footer note
        story.append(Spacer(1, 0.2*inch))
        footer_note = 'This document contains confidential and proprietary information intended solely for the recipient. By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, distribute, or use any information herein for purposes other than those expressly authorized. Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, please notify the sender immediately and delete this document from your system Finished Product Specification Form – Updated 12/10/2025 (GDM) – Reviewed by GDM – Effective Date 12/10/2025 – Doc No. 3.3 - 01.'
        story.append(Paragraph(footer_note, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#666666'))))
        
        story.append(PageBreak())
        
        # Checklist page
        story.append(header_table)
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('FINISHED PRODUCT SPECIFICATION CHECKLIST', title_style))
        story.append(Spacer(1, 0.3*inch))
        
        story.append(Paragraph(f'<b>Product Name:</b> {item.name}', field_value_style))
        story.append(Spacer(1, 0.2*inch))
        
        checklist_items = [
            ('MSDS Created', fps.msds_created),
            ('Commercial Spec Created / COA', fps.commercial_spec_created),
            ('Label Template Created', fps.label_template_created),
            ('Product evaluated for micro growth', fps.micro_growth_evaluated),
            ('Product Added to Kosher Letter', fps.kosher_letter_added),
            ('Initial HACCP Plan Created', fps.haccp_plan_created),
        ]
        
        for label, checked in checklist_items:
            checkmark = '✓' if checked else '☐'
            story.append(Paragraph(f'{checkmark} {label}', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('<b>Processing Requirements</b><br/>(i.e. specific tank or mixer, how long should product be mixed, allergen considerations, temperature requirements)', field_label_style))
        story.append(Paragraph(fps.processing_requirements or '', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph('<b>Product Formula</b>', field_label_style))
        # Get formula if exists
        try:
            formula = Formula.objects.get(finished_good=item)
            formula_text = f"Version: {formula.version}\n\n"
            for ingredient in formula.ingredients.all():
                formula_text += f"{ingredient.item.name}: {ingredient.percentage}%\n"
            story.append(Paragraph(formula_text.replace('\n', '<br/>'), field_value_style))
        except Formula.DoesNotExist:
            story.append(Paragraph('No formula assigned', field_value_style))
        
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f'<b>Name and Title of Person Completing Form:</b><br/>{fps.completed_by_name or ""}', field_value_style))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f'<b>Signature and Date:</b><br/>{fps.completed_by_signature or ""} {fps.completed_date or ""}', field_value_style))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(footer_note, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#666666'))))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Save PDF to file
        if not fps.fps_pdf:
            from django.core.files.base import ContentFile
            filename = f"FPS_{item.sku}_{item.name.replace(' ', '_')}.pdf"
            fps.fps_pdf.save(filename, ContentFile(pdf_content), save=True)
        
        # Return PDF as response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="FPS_{item.sku}.pdf"'
        return response

