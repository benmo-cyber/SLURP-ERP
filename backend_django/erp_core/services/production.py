"""Production batch workflow services."""

from django.db import transaction
from django.utils import timezone

from erp_core.models import (
    InventoryTransaction,
    Lot,
    ProductionBatch,
    ProductionBatchInput,
    ProductionBatchOutput,
)
from erp_core.services.inventory import WorkflowError
from erp_core.services.numbers import generate_batch_number, generate_lot_number


def _to_lbs(quantity, uom):
    if uom == 'kg':
        return quantity * 2.20462
    return quantity


def create_production_batch(*, batch_type, finished_good_item, quantity_produced, inputs_data, notes=''):
    batch_number = generate_batch_number(batch_type)
    total_input_lbs = 0.0
    validated_inputs = []

    for row in inputs_data:
        lot = Lot.objects.get(id=row['lot_id'])
        qty = float(row['quantity_used'])
        if lot.quantity_remaining < qty:
            raise WorkflowError(
                f'Insufficient qty in lot {lot.lot_number}: '
                f'{lot.quantity_remaining} available, {qty} requested.'
            )
        total_input_lbs += _to_lbs(qty, lot.item.unit_of_measure)
        validated_inputs.append((lot, qty))

    if abs(total_input_lbs - quantity_produced) > 0.01:
        raise WorkflowError(
            f'Input total ({total_input_lbs:.2f} lbs) must equal '
            f'quantity to produce ({quantity_produced:.2f} lbs).'
        )

    with transaction.atomic():
        batch = ProductionBatch.objects.create(
            batch_number=batch_number,
            batch_type=batch_type,
            finished_good_item=finished_good_item,
            quantity_produced=quantity_produced,
            status='in_progress',
            notes=notes,
        )
        for lot, qty in validated_inputs:
            ProductionBatchInput.objects.create(batch=batch, lot=lot, quantity_used=qty)
            InventoryTransaction.objects.create(
                transaction_type='production',
                lot=lot,
                quantity=-qty,
                reference_number=batch.batch_number,
                notes=f'Batch {batch.batch_number} input',
            )
            lot.quantity_remaining -= qty
            lot.save()

        if batch_type == 'repack':
            output_qty = quantity_produced
            lot_number = generate_lot_number()
            new_lot = Lot.objects.create(
                lot_number=lot_number,
                item=finished_good_item,
                quantity=output_qty,
                quantity_remaining=output_qty,
                received_date=timezone.now(),
                status='accepted',
            )
            ProductionBatchOutput.objects.create(
                batch=batch, lot=new_lot, quantity_produced=output_qty
            )
            InventoryTransaction.objects.create(
                transaction_type='production',
                lot=new_lot,
                quantity=output_qty,
                reference_number=batch.batch_number,
                notes=f'Repack batch {batch.batch_number} output',
            )
    return batch


def close_production_batch(batch, quantity_actual=None, variance=0, wastes=0, spills=0):
    if batch.status == 'closed':
        raise WorkflowError('Batch is already closed.')
    batch.status = 'closed'
    batch.closed_date = timezone.now()
    batch.quantity_actual = quantity_actual or batch.quantity_produced
    batch.variance = variance
    batch.wastes = wastes
    batch.spills = spills
    batch.save()

    if batch.batch_type == 'production' and not batch.outputs.exists():
        output_qty = batch.quantity_actual or batch.quantity_produced
        lot_number = generate_lot_number()
        new_lot = Lot.objects.create(
            lot_number=lot_number,
            item=batch.finished_good_item,
            quantity=output_qty,
            quantity_remaining=output_qty,
            received_date=timezone.now(),
            status='accepted',
        )
        ProductionBatchOutput.objects.create(
            batch=batch, lot=new_lot, quantity_produced=output_qty
        )
        InventoryTransaction.objects.create(
            transaction_type='production',
            lot=new_lot,
            quantity=output_qty,
            reference_number=batch.batch_number,
            notes=f'Production batch {batch.batch_number} output',
        )
    return batch


def reverse_production_batch(batch):
    if batch.status == 'closed':
        raise WorkflowError('Cannot reverse a closed batch via UNFK.')

    with transaction.atomic():
        for inp in batch.inputs.select_related('lot'):
            lot = inp.lot
            lot.quantity_remaining += inp.quantity_used
            lot.save()
        for out in batch.outputs.all():
            out.lot.delete()
        batch.delete()
