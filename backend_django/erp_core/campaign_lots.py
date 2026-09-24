"""Campaign lot (YYWW + parent product code) for production batches."""
from __future__ import annotations

from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from erp_core.models import CampaignLot, ProductionBatch
from erp_core.sku_family import parse_sku_family


def item_parent_product_code(item) -> str:
    """Parent family code used as CampaignLot.product_code (e.g. D1307)."""
    if item is None:
        return ""
    code = (getattr(item, "sku_parent_code", None) or "").strip().upper()
    if code:
        return code
    parent, _pack = parse_sku_family(
        getattr(item, "sku", None) or "",
        product_category=getattr(item, "product_category", None),
        item_type=getattr(item, "item_type", None),
    )
    if parent:
        return parent.strip().upper()
    return (getattr(item, "sku", None) or "").strip().upper()


def _anchor_date_for_batch(batch: ProductionBatch) -> date:
    pd = getattr(batch, "production_date", None)
    if pd is None:
        return timezone.localdate()
    if isinstance(pd, datetime):
        return timezone.localtime(pd).date() if timezone.is_aware(pd) else pd.date()
    if isinstance(pd, date):
        return pd
    return timezone.localdate()


def campaign_code_for_anchor(anchor: date, product_code: str) -> str:
    iso = anchor.isocalendar()
    yy = str(iso[0])[-2:]
    ww = f"{iso[1]:02d}"
    return f"{yy}{ww}{(product_code or '').strip().upper()}"


def preview_campaign_code(batch: ProductionBatch) -> str:
    """
    Current campaign code if linked, else YYWW+parent implied by production_date.
    Empty when not a production batch or parent cannot be resolved.
    """
    if getattr(batch, "batch_type", None) != "production":
        return ""
    if getattr(batch, "campaign_id", None):
        camp = getattr(batch, "campaign", None)
        if camp is not None and camp.campaign_code:
            return camp.campaign_code
    item = getattr(batch, "finished_good_item", None)
    product_code = item_parent_product_code(item)
    if not product_code:
        return ""
    return campaign_code_for_anchor(_anchor_date_for_batch(batch), product_code)


def get_or_create_campaign(*, item, product_code: str, anchor: date) -> CampaignLot:
    """Get existing CampaignLot by code, or create for item + parent + ISO week."""
    product_code = (product_code or "").strip().upper()
    if not product_code:
        raise ValueError("Parent product code is required for a campaign lot.")
    code = campaign_code_for_anchor(anchor, product_code)
    existing = CampaignLot.objects.filter(campaign_code=code).first()
    if existing is not None:
        return existing
    campaign = CampaignLot(
        item=item,
        anchor_date=anchor,
        product_code=product_code,
        notes="",
    )
    campaign.save()
    return campaign


def link_batches_to_campaign(batch_ids: list[int]) -> tuple[CampaignLot, list[ProductionBatch]]:
    """
    Link production batches into one campaign (same parent family + same ISO week
    of production_date). Returns (campaign, linked batches).
    """
    if not batch_ids:
        raise ValueError("Select at least one production batch.")

    batches = list(
        ProductionBatch.objects.filter(pk__in=batch_ids)
        .select_related("finished_good_item", "campaign")
        .order_by("id")
    )
    if len(batches) != len(set(batch_ids)):
        raise ValueError("One or more selected batches were not found.")

    for b in batches:
        if b.batch_type != "production":
            raise ValueError(
                f"{b.batch_number} is a {b.batch_type} ticket — campaigns are for production only."
            )

    parents = []
    weeks = []
    for b in batches:
        parent = item_parent_product_code(b.finished_good_item)
        if not parent:
            sku = b.finished_good_item.sku if b.finished_good_item_id else "?"
            raise ValueError(
                f"{b.batch_number} ({sku}) has no parent product code. "
                "Set sku_parent_code before linking a campaign."
            )
        parents.append(parent)
        weeks.append(_anchor_date_for_batch(b).isocalendar()[:2])

    if len(set(parents)) > 1:
        raise ValueError(
            "Selected batches must share the same parent family "
            f"(found {', '.join(sorted(set(parents)))})."
        )
    if len(set(weeks)) > 1:
        raise ValueError(
            "Selected batches must share the same ISO production week. "
            "Unlink or move production dates before linking across weeks."
        )

    product_code = parents[0]
    anchor = _anchor_date_for_batch(batches[0])
    item = batches[0].finished_good_item

    with transaction.atomic():
        campaign = get_or_create_campaign(
            item=item, product_code=product_code, anchor=anchor
        )
        for b in batches:
            if b.campaign_id != campaign.id:
                b.campaign = campaign
                b.save(update_fields=["campaign", "updated_at"])

    return campaign, batches


def unlink_batches_from_campaign(batch_ids: list[int]) -> list[ProductionBatch]:
    """Clear campaign on selected production batches (does not delete CampaignLot)."""
    if not batch_ids:
        raise ValueError("Select at least one batch to unlink.")

    batches = list(
        ProductionBatch.objects.filter(pk__in=batch_ids).select_related("campaign")
    )
    if not batches:
        raise ValueError("No matching batches found.")

    with transaction.atomic():
        for b in batches:
            if b.campaign_id:
                b.campaign = None
                b.save(update_fields=["campaign", "updated_at"])
    return batches
