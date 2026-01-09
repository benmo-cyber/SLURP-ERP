from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime
from .models import (
    Item, Lot, ProductionBatch, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, LotNumberSequence, Vendor, VendorHistory,
    SupplierSurvey, SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification
)
from .serializers import (
    ItemSerializer, LotSerializer, ProductionBatchSerializer,
    FormulaSerializer, FormulaItemSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    SalesOrderSerializer, SalesOrderItemSerializer,
    InventoryTransactionSerializer, VendorSerializer, VendorHistorySerializer,
    SupplierSurveySerializer, SupplierDocumentSerializer, TemporaryExceptionSerializer,
    CostMasterSerializer, CostMasterHistorySerializer, AccountSerializer,
    FinishedProductSpecificationSerializer
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
        
        # Update the item
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
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
        from .models import SalesOrderItem, ProductionBatchInput, Item, CostMaster, PurchaseOrder
        
        # Get all items
        items = Item.objects.all()
        inventory_data = []
        sku_master_data = {}  # Store master SKU aggregations
        
        # Pre-calculate item-level sales allocations
        item_sales_allocations = {}
        for item_id in items.values_list('id', flat=True):
            total_allocated = SalesOrderItem.objects.filter(
                item_id=item_id,
                sales_order__status__in=['draft', 'allocated', 'shipped']
            ).aggregate(
                total=Sum('quantity_allocated')
            )['total'] or 0.0
            item_sales_allocations[item_id] = total_allocated
        
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
            cost_masters = CostMaster.objects.filter(wwi_product_code=sku)
            
            # Get all lots for all items with this SKU
            item_ids = [i.id for i in sku_items]
            item_lots = Lot.objects.filter(
                item_id__in=item_ids,
                status='accepted'
            ).select_related('item')
            
            # Build a map of vendor -> lots by checking PO vendor
            vendor_lots_map = {}
            lots_without_vendor = []
            
            for lot in item_lots:
                vendor_name = None
                if lot.po_number:
                    try:
                        po = PurchaseOrder.objects.get(po_number=lot.po_number)
                        vendor_name = po.vendor_customer_name
                    except PurchaseOrder.DoesNotExist:
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
                
                # Calculate allocated to production (sum across all vendor lots)
                allocated_to_production = ProductionBatchInput.objects.filter(
                    lot__in=vendor_lots,
                    batch__status='open'
                ).aggregate(
                    total=Sum('quantity_used')
                )['total'] or 0.0
                
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
                
                # Get on_order from the vendor-specific item
                on_order = vendor_item.on_order if vendor_item else 0.0
                
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
                    'total_quantity': 0.0,
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
        print(f"[INVENTORY DEBUG] Returning {len(inventory_data)} SKU entries")
        if inventory_data:
            print(f"[INVENTORY DEBUG] First entry: SKU={inventory_data[0].get('item_sku')}, level={inventory_data[0].get('level')}")
        else:
            print(f"[INVENTORY DEBUG] WARNING: No inventory data to return!")
            print(f"[INVENTORY DEBUG] Items in DB: {items.count()}, SKUs grouped: {len(items_by_sku)}")
        
        return Response(inventory_data)
    
    def create(self, request, *args, **kwargs):
        # Generate lot number automatically
        lot_number = generate_lot_number()
        
        # Get lot_status from request data (renamed to avoid shadowing status module)
        lot_status = request.data.get('status', 'accepted')
        
        # Create the lot
        serializer = self.get_serializer(data={
            **request.data,
            'lot_number': lot_number,
            'status': lot_status,
        })
        serializer.is_valid(raise_exception=True)
        lot = serializer.save()
        
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
    
    @action(detail=True, methods=['post'])
    def reverse_check_in(self, request, pk=None):
        lot = self.get_object()
        
        # Create reverse transaction
        InventoryTransaction.objects.create(
            transaction_type='adjustment',
            lot=lot,
            quantity=-lot.quantity_remaining,
            notes='Reverse check-in',
        )
        
        # Delete the lot
        lot.delete()
        
        return Response({'message': 'Check-in reversed successfully'}, status=status.HTTP_200_OK)


class ProductionBatchViewSet(viewsets.ModelViewSet):
    queryset = ProductionBatch.objects.select_related('finished_good_item').all()
    serializer_class = ProductionBatchSerializer
    
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        batch = self.get_object()
        
        # Reverse all inventory transactions for this batch
        from .models import InventoryTransaction
        transactions = InventoryTransaction.objects.filter(
            production_batch=batch
        )
        
        for transaction in transactions:
            # Create reverse transaction
            InventoryTransaction.objects.create(
                transaction_type='adjustment',
                lot=transaction.lot,
                quantity=-transaction.quantity,
                notes=f'Reverse batch {batch.batch_number}',
            )
        
        # Delete the batch
        batch.delete()
        
        return Response({'message': 'Batch ticket reversed successfully'}, status=status.HTTP_200_OK)


class FormulaViewSet(viewsets.ModelViewSet):
    queryset = Formula.objects.select_related('finished_good').prefetch_related('ingredients__item').all()
    serializer_class = FormulaSerializer


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
        
        # Handle customer reference number
        # If customer_reference_number is not provided, use customer_id as default
        if not data.get('customer_reference_number') and data.get('customer_id'):
            data['customer_reference_number'] = data.get('customer_id')
        
        # Create the sales order
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        sales_order = serializer.save()
        
        # Create sales order items
        for item_data in items_data:
            SalesOrderItem.objects.create(
                sales_order=sales_order,
                **item_data
            )
        
        # Return the created sales order with items
        serializer = self.get_serializer(sales_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class InventoryTransactionViewSet(viewsets.ModelViewSet):
    queryset = InventoryTransaction.objects.select_related('lot__item').all()
    serializer_class = InventoryTransactionSerializer


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

