"""
Batch ticket PDF generation.

CANONICAL VERSION: Task 1 (template logo only). Task 2 (header: batch number
redaction, Pack Size on own line, Calibri 10 + bold "Pack Size:"). Task 3 (pick
list: raw material column, combined lot column, centered in cells).

To copy the template EXACTLY: put your Batch Ticket template PDF in
  backend_django/batch_ticket_template/
The system will open that PDF and insert only the variable data (Product ID,
SKU, batch number, pick list rows, etc.) at the exact positions where the
template has blanks — so layout, tables, and design stay identical.

Requires: PyMuPDF (pip install pymupdf) for template filling.
Fallback: if no template or PyMuPDF unavailable, a flowable PDF is built.
"""
from pathlib import Path
from io import BytesIO
import tempfile
import os
import shutil
import logging

logger = logging.getLogger(__name__)

# Fixed confidentiality statement — appears ONLY in footer of each page (cannot move)
CONFIDENTIALITY_FOOTER = (
    "This document contains confidential and proprietary information intended solely for the recipient. "
    "By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, "
    "distribute, or use any information herein for purposes other than those expressly authorized. "
    "Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, "
    "please notify the sender immediately and delete this document from your system."
)


def _is_indirect_material(item):
    """Return True if item is an indirect material (packaging, etc.). Handles DB value variants."""
    if item is None:
        return False
    t = (getattr(item, 'item_type', None) or '').strip().lower()
    return t == 'indirect_material' or 'indirect' in t


def get_indirect_materials_for_batch(batch):
    """
    Return list of dicts for indirect materials consumed by this batch: {packaging, lot, qty, uom}.
    Merges all sources (LotTransactionLog, batch.inputs, InventoryTransaction) and dedupes so we
    never miss data regardless of which path recorded it.
    """
    out = []
    seen = set()

    def add_row(packaging, lot_number, qty_used, key=None):
        q = float(qty_used)
        key = key or (str(lot_number), round(q, 4))
        if key in seen:
            return
        seen.add(key)
        qty_str = f"{int(q)}" if q == int(q) else f"{q:.2f}"
        out.append({
            'packaging': (packaging or '').strip(),
            'lot': (lot_number or '—').strip(),
            'qty': qty_str,
            'uom': 'EA',
        })

    # 1) LotTransactionLog by batch_id (same as "consumed in inventory")
    try:
        from .models import LotTransactionLog
        for log in LotTransactionLog.objects.filter(
            batch_id=batch.id,
            transaction_type='indirect_material_consumption',
        ).select_related('lot__item').order_by('logged_at'):
            if not log.lot:
                continue
            item = log.lot.item
            qty_used = abs(float(log.quantity_change))
            packaging = (getattr(item, 'description', None) or getattr(item, 'name', None) or getattr(item, 'sku', None) or '')
            add_row(packaging, log.lot.lot_number, qty_used, (log.lot_id, round(qty_used, 4)))
    except Exception as e:
        logger.warning("get_indirect_materials_for_batch: LotTransactionLog failed for batch %s: %s", getattr(batch, 'batch_number', batch.id), e)

    # 2) batch.inputs where item is indirect (same as view), or UoM is EA (packaging)
    try:
        for batch_input in batch.inputs.select_related('lot__item').all():
            item = getattr(batch_input.lot, 'item', None)
            if not item:
                continue
            uom = (getattr(item, 'unit_of_measure', None) or '').strip().lower()
            if not _is_indirect_material(item) and uom not in ('ea', 'e.a.', 'each'):
                continue
            packaging = (getattr(item, 'description', None) or getattr(item, 'name', None) or getattr(item, 'sku', None) or '')
            add_row(packaging, batch_input.lot.lot_number, batch_input.quantity_used, (batch_input.lot_id, round(float(batch_input.quantity_used), 4)))
    except Exception as e:
        logger.warning("get_indirect_materials_for_batch: batch.inputs failed for batch %s: %s", getattr(batch, 'batch_number', batch.id), e)

    # 3) InventoryTransaction by reference_number
    try:
        from .models import InventoryTransaction
        for tx in InventoryTransaction.objects.filter(
            transaction_type='indirect_material_consumption',
            reference_number=batch.batch_number,
        ).select_related('lot__item'):
            if not tx.lot or not _is_indirect_material(tx.lot.item):
                continue
            item = tx.lot.item
            qty_used = abs(float(tx.quantity))
            packaging = (getattr(item, 'description', None) or getattr(item, 'name', None) or getattr(item, 'sku', None) or '')
            add_row(packaging, tx.lot.lot_number, qty_used, (tx.lot_id, round(qty_used, 4)))
    except Exception as e:
        logger.warning("get_indirect_materials_for_batch: InventoryTransaction failed for batch %s: %s", getattr(batch, 'batch_number', batch.id), e)

    if out:
        logger.info("get_indirect_materials_for_batch: batch %s has %s indirect row(s)", getattr(batch, 'batch_number', batch.id), len(out))
    return out


def get_batch_ticket_template_path():
    """
    Return the path to the Batch Ticket template file, or None.
    Search order:
    1. BATCH_TICKET_TEMPLATE_PATH env var (path to a specific file, or to a folder to search)
    2. Project root (WWI ERP folder) — Batch ticket template.pdf lives here
    3. backend_django/batch_ticket_template/
    4. Sensitive/ at project root
    """
    base = Path(__file__).resolve().parent.parent.parent  # WWI ERP (project root)
    backend = Path(__file__).resolve().parent.parent  # backend_django
    # Prefer PDF so our filler runs on the template; avoid using .docx (conversion can look different)
    names = [
        'Batch_ticket_template.pdf',
        'Batch Ticket template.pdf',
        'Batch ticket template.pdf',
        'Batch Ticket (BP-13).pdf',
        'Batch Ticket.pdf',
        'batch_ticket.pdf',
        'BatchTicket.pdf',
        'Batch_ticket_template.docx',
        'Batch_ticket_template.doc',
        'Batch Ticket template.docx',
        'Batch ticket template.docx',
        'Batch Ticket template.doc',
        'Batch Ticket (BP-13).docx',
        'Batch Ticket (BP-13).doc',
    ]

    # 1) Explicit path from environment
    env_path = os.environ.get('BATCH_TICKET_TEMPLATE_PATH') or os.environ.get('BATCH_TICKET_TEMPLATE_DIR')
    if env_path:
        p = Path(env_path).resolve()
        if p.is_file() and p.suffix.lower() in ('.pdf', '.docx', '.doc'):
            return str(p)
        if p.is_dir():
            for name in names:
                candidate = p / name
                if candidate.exists():
                    return str(candidate)
            for f in sorted(p.glob('*'), key=lambda x: (0 if x.suffix.lower() == '.pdf' else 1, x.name)):
                if f.name.startswith('~$'):
                    continue  # skip Word/Excel lock files
                if f.suffix.lower() in ('.pdf', '.docx', '.doc') and 'batch' in f.name.lower():
                    return str(f)

    # 2) Project root (WWI ERP folder) — canonical template location
    for name in names:
        path = base / name
        if path.exists():
            return str(path)
    for f in sorted(base.glob('*'), key=lambda p: (0 if p.suffix.lower() == '.pdf' else 1, p.name)):
        if f.name.startswith('~$'):
            continue
        if f.suffix.lower() in ('.pdf', '.docx', '.doc') and 'batch' in f.name.lower():
            return str(f)

    # 3) backend_django/batch_ticket_template/
    template_dir = backend / 'batch_ticket_template'
    if template_dir.is_dir():
        for name in names:
            path = template_dir / name
            if path.exists():
                return str(path)
        for f in sorted(template_dir.glob('*'), key=lambda p: (0 if p.suffix.lower() == '.pdf' else 1, p.name)):
            if f.name.startswith('~$'):
                continue  # skip Word/Excel lock files
            if f.suffix.lower() in ('.pdf', '.docx', '.doc'):
                return str(f)

    # 4) Sensitive folder at project root
    sensitive = base / 'Sensitive'
    if sensitive.is_dir():
        for name in names:
            path = sensitive / name
            if path.exists():
                return str(path)
    return None


def _batch_ticket_logo_path_and_copy():
    """
    Get path to logo for batch tickets. If logo is in Sensitive or frontend/public,
    copy it to batch_ticket_template so it is available and appears correctly.
    Returns path to logo file or None.
    """
    backend = Path(__file__).resolve().parent.parent
    base = backend.parent
    template_dir = backend / 'batch_ticket_template'
    names = ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']
    # 1) Already in template folder
    if template_dir.exists():
        for name in names:
            p = template_dir / name
            if p.exists():
                return str(p)
    # 2) Copy from Sensitive or frontend/public into template folder
    for folder, dir_ok in [(base / 'Sensitive', True), (base / 'frontend' / 'public', (base / 'frontend' / 'public').exists())]:
        if not dir_ok or not folder.exists():
            continue
        for name in names:
            src = folder / name
            if src.exists():
                try:
                    template_dir.mkdir(parents=True, exist_ok=True)
                    dest = template_dir / name
                    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                        shutil.copy2(src, dest)
                    return str(dest)
                except Exception:
                    return str(src)
    return None


def _convert_docx_to_pdf(docx_path: str):
    """
    Convert a Word document (.docx or .doc) to a PDF file.
    Returns the path to the temporary PDF file, or None on failure.
    Caller should delete the temp file when done.
    """
    path = Path(docx_path).resolve()
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    if suffix not in ('.docx', '.doc'):
        return None

    out_dir = tempfile.mkdtemp()
    out_pdf = Path(out_dir).resolve() / (path.stem + '.pdf')

    # 1) Try docx2pdf (Windows, uses Microsoft Word via COM)
    try:
        import docx2pdf
        docx2pdf.convert(str(path), str(out_pdf))
        if out_pdf.exists():
            return str(out_pdf)
    except Exception:
        pass

    # 2) Try LibreOffice headless
    try:
        import subprocess
        cmd = [
            'soffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', out_dir,
            str(path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)
        if out_pdf.exists():
            return str(out_pdf)
        # LibreOffice sometimes names output by full path stem
        for f in Path(out_dir).glob('*.pdf'):
            return str(f)
    except Exception:
        pass

    try:
        os.rmdir(out_dir)
    except Exception:
        pass
    return None


def _get_template_pdf_path(template_path: str):
    """
    Return a path to a PDF to use as the template first page.
    If template_path is .docx/.doc, convert to PDF (caller must delete temp file).
    """
    path = Path(template_path)
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return str(path), None  # (pdf_path, temp_dir_to_cleanup)
    if suffix in ('.docx', '.doc'):
        pdf_path = _convert_docx_to_pdf(template_path)
        if pdf_path:
            return pdf_path, os.path.dirname(pdf_path)  # temp_dir for cleanup
    return None, None


def _draw_fixed_footer_confidentiality(page, fontname="helv", fontsize=5, color=(0, 0, 0), page_num=None):
    """Draw the confidentiality statement in a fixed footer zone (bottom of page). Leaves space below for version/update line so no overlap."""
    try:
        import fitz
        # Letter: 612 x 792. Confidentiality in footer; leave 26 pt at bottom for "Batch Ticket - Updated..." and "-- 1 of 2 --"
        footer_bottom_reserved = 26
        rect = fitz.Rect(36, 792 - 68, 576, 792 - footer_bottom_reserved)
        shape = page.new_shape()
        shape.insert_textbox(rect, CONFIDENTIALITY_FOOTER, fontsize=fontsize, fontname=fontname, color=color, align=fitz.TEXT_ALIGN_LEFT)
        shape.commit()
        if page_num in (1, 2):
            page_num_text = f"-- {page_num} of 2 --"
            page.insert_text((270, 792 - 8), page_num_text, fontsize=7, fontname=fontname, color=color)
    except Exception:
        try:
            page.insert_text((36, 792 - 24), CONFIDENTIALITY_FOOTER[:90] + "...", fontsize=fontsize, fontname=fontname, color=color)
            page.insert_text((36, 792 - 14), "Unauthorized use or disclosure may result in legal action.", fontsize=fontsize, fontname=fontname, color=color)
        except Exception:
            pass


def _redact_batch_number_placeholder(page):
    """White-out template placeholder 'BT-YYMMDD-Seq' (and similar) so the actual batch number replaces it."""
    try:
        import fitz
        blocks = page.get_text("dict").get("blocks", [])
        rects = []
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip()
                    tl = t.lower()
                    # Match placeholder only (not real batch numbers like BT-20260219-010): BT-YYMMDD-Seq, BT-YMMDD-Seq, etc.
                    is_placeholder = (
                        len(t) <= 20 and tl.startswith("bt") and "seq" in tl and
                        ("yymmdd" in tl or "ymmdd" in tl)
                    )
                    if t and is_placeholder:
                        bbox = span.get("bbox")
                        if bbox and len(bbox) >= 4:
                            rects.append(fitz.Rect(bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2))
        if rects:
            shape = page.new_shape()
            for r in rects:
                shape.draw_rect(r)
            # fill white, no stroke (width=0) so no visible border
            shape.finish(fill=(1, 1, 1), width=0)
            shape.commit()
    except Exception:
        pass


def _redact_confidentiality_from_body(page):
    """White-out any confidentiality paragraph in the body so it only appears in the footer. Skip footer zone (bottom 70 pt)."""
    try:
        import fitz
        footer_top_y = 792 - 70
        rects = []
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").lower()
                    if "confidential" in t or "proprietary" in t or "intended solely for the recipient" in t:
                        bbox = span.get("bbox")
                        if bbox and len(bbox) >= 4 and bbox[1] < footer_top_y:
                            rects.append(fitz.Rect(bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2))
        if rects:
            shape = page.new_shape()
            for r in rects:
                shape.draw_rect(r)
                shape.finish(fill=(1, 1, 1), width=0)
            shape.commit()
    except Exception:
        pass


def _find_text_bbox(page, search_text):
    """Return (x1, y0, fontsize) for placing value after the label, or None. Uses PyMuPDF page.
    Tries exact label first, then label without colon, then key phrase (e.g. 'product id') so
    Word-rendered PDFs with slight differences still match."""
    def norm(s):
        return (s or "").replace("\ufb01", "fi").replace("\u01a0", "t").replace("\u01a1", "t").lower()
    try:
        raw = search_text.strip()
        want_exact = norm(raw)
        want_no_colon = norm(raw.rstrip(":").strip())
        key_phrase = want_no_colon.split(":")[0].strip() if ":" in raw else want_no_colon
        candidates = [want_exact, want_no_colon, key_phrase]
        for want in candidates:
            if not want or len(want) < 2:
                continue
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = norm(span.get("text", ""))
                        if want in text or (len(want) >= 4 and "date" in want and "date" in text and "product id" not in text and want[:5] in text):
                            bbox = span.get("bbox")
                            if bbox and len(bbox) >= 4:
                                fontsize = span.get("size", 10)
                                return (bbox[2], bbox[1], fontsize)
    except Exception:
        pass
    return None


def _find_label_bbox(page, search_text):
    """Return (x0, y0, x1, y1, fontsize) for the label, or None. Used to get left edge for alignment."""
    def norm(s):
        return (s or "").replace("\ufb01", "fi").replace("\u01a0", "t").replace("\u01a1", "t").lower()
    try:
        raw = search_text.strip()
        want_no_colon = norm(raw.rstrip(":").strip())
        key_phrase = want_no_colon.split(":")[0].strip() if ":" in raw else want_no_colon
        for want in [norm(raw), want_no_colon, key_phrase]:
            if not want or len(want) < 2:
                continue
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = norm(span.get("text", ""))
                        if want in text:
                            bbox = span.get("bbox")
                            if bbox and len(bbox) >= 4:
                                return (bbox[0], bbox[1], bbox[2], bbox[3], span.get("size", 10))
    except Exception:
        pass
    return None


def _get_calibri_font_paths():
    """Return (calibri_regular_path, calibri_bold_path) for Calibri (Body) size 10. Windows Fonts folder."""
    windir = os.environ.get("WINDIR", "C:\\Windows")
    fonts_dir = Path(windir) / "Fonts"
    candidates = [
        (fonts_dir / "calibri.ttf", fonts_dir / "calibrib.ttf"),
        (fonts_dir / "Calibri.ttf", fonts_dir / "Calibri Bold.ttf"),
        (fonts_dir / "calibri.ttf", fonts_dir / "Calibri Bold.ttf"),
    ]
    for reg, bold in candidates:
        if reg.exists() and bold.exists():
            return str(reg), str(bold)
    if (fonts_dir / "calibri.ttf").exists():
        reg = fonts_dir / "calibri.ttf"
        bold = fonts_dir / "calibrib.ttf"
        if bold.exists():
            return str(reg), str(bold)
        return str(reg), None
    return None, None


def _draw_pack_size_line(page, x, y, pack_size_str, color=(0, 0, 0)):
    """
    Draw "Pack Size: <value>" at (x, y) using Calibri (Body) size 10 with "Pack Size:" in bold.
    Uses TextWriter + Font so custom Calibri/Calibri Bold are used; falls back to helv/helv-bold if unavailable.
    """
    import fitz
    pack_val = (pack_size_str or "")[:16]
    calibri_reg, calibri_bold = _get_calibri_font_paths()
    try:
        if calibri_reg and calibri_bold:
            font_reg = fitz.Font(fontfile=calibri_reg)
            font_bold = fitz.Font(fontfile=calibri_bold)
        else:
            font_reg = fitz.Font("helv")
            font_bold = fitz.Font("helv-bold")
        if not getattr(font_reg, "is_writable", True):
            font_reg = fitz.Font("helv")
        if not getattr(font_bold, "is_writable", True):
            font_bold = fitz.Font("helv-bold")
        tw = fitz.TextWriter(page.rect, color=color)
        tw.append((x, y), "Pack Size: ", font=font_bold, fontsize=10)
        tw.append(tw.last_point, pack_val, font=font_reg, fontsize=10)
        tw.write_text(page)
    except Exception:
        page.insert_text((x, y), "Pack Size: " + pack_val, fontsize=10, fontname="helv", color=color)


def _redact_pack_size_label_on_batch_size_line(page):
    """White-out 'Pack Size:' when it is on the same line as 'Batch Size:' so it doesn't overlap the 700.00 lbs."""
    try:
        import fitz
        pos_bs = _find_text_bbox(page, "Batch Size:")
        if not pos_bs:
            return
        _, y_bs, _ = pos_bs
        y_tolerance = 5
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").lower()
                    if "pack size" in t and ":" in t:
                        bbox = span.get("bbox")
                        if bbox and len(bbox) >= 4 and abs(bbox[1] - y_bs) < y_tolerance:
                            shape = page.new_shape()
                            shape.draw_rect(fitz.Rect(bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2))
                            shape.finish(fill=(1, 1, 1), width=0)
                            shape.commit()
                            return
    except Exception:
        pass


def _find_header_column_xs(page):
    """Detect Batch Size / Pack Size positions so we can place values at separate x (no overlap)."""
    try:
        pos_bs = _find_text_bbox(page, "Batch Size:")
        pos_ps = _find_text_bbox(page, "Pack Size:")
        if not pos_bs or not pos_ps:
            return None
        x_bs, y_bs, fs = pos_bs
        x_ps, y_ps, _ = pos_ps
        gap = 8
        batch_size_x = x_bs + gap
        pack_size_x = max(x_ps + gap, x_bs + gap + 95)
        return {
            "batch_size_x": batch_size_x,
            "pack_size_x": pack_size_x,
            "batch_size_y": y_bs,
            "pack_size_y": y_ps,
            "fs": fs,
        }
    except Exception:
        return None


def _get_header_layout(page):
    """
    Get positions for each header line. Batch Size and Pack Size each get their own
    x (right after their label) and are on separate lines: Batch Size then Pack Size below.
    """
    try:
        pos_id = _find_text_bbox(page, "Product ID:")
        pos_sku = _find_text_bbox(page, "SKU:")
        pos_bn = _find_text_bbox(page, "Batch Number:")
        pos_bs = _find_text_bbox(page, "Batch Size:")
        pos_ps = _find_text_bbox(page, "Pack Size:")
        if not pos_id:
            return None
        x_id, y_id, fs = pos_id
        gap = 8
        line_spacing = 14
        # Value column x for Product ID, SKU, Batch Number: right of each label or max of first three
        label_right_edges = [pos_id[0], pos_sku[0] if pos_sku else 0, pos_bn[0] if pos_bn else 0]
        value_x = max(label_right_edges) + gap
        y_sku = pos_sku[1] if pos_sku else y_id + line_spacing
        y_bn = pos_bn[1] if pos_bn else y_sku + line_spacing
        y_bs = pos_bs[1] if pos_bs else y_bn + line_spacing
        # Batch Size and Pack Size on separate lines: Batch Size first, Pack Size on next line
        y_pack_size = y_bs + line_spacing
        batch_size_x = (pos_bs[0] + gap) if pos_bs else value_x
        # Left edge of "Batch Size:" so we can draw "Pack Size: 40 lb" aligned on line 2
        bbox_bs = _find_label_bbox(page, "Batch Size:")
        header_left_x = bbox_bs[0] if bbox_bs else value_x
        return {
            "value_x": value_x,
            "batch_size_x": batch_size_x,
            "header_left_x": header_left_x,
            "y_product_id": y_id,
            "y_sku": y_sku,
            "y_batch_number": y_bn,
            "y_batch_size": y_bs,
            "y_pack_size": y_pack_size,
            "fs": fs,
        }
    except Exception:
        return None


def _wrap_text_to_width(font, text, fontsize, max_width_pt):
    """Split text into lines that fit within max_width_pt. Long single words are truncated with … to fit."""
    if not (text and max_width_pt > 0):
        return [text] if text else []
    text = (text or "").replace("\n", " ").replace("\r", "").strip()
    if not text:
        return []
    space_w = font.text_length(" ", fontsize=fontsize)

    def truncate_to_fit(s, max_pt):
        if font.text_length(s, fontsize=fontsize) <= max_pt:
            return s
        out = ""
        for c in s:
            if font.text_length(out + c + "…", fontsize=fontsize) > max_pt:
                return out + "…" if out else "…"
            out += c
        return out

    words = text.split()
    lines = []
    current = []
    current_width = 0
    for word in words:
        w = font.text_length(word, fontsize=fontsize)
        if w > max_width_pt:
            if current:
                lines.append(" ".join(current))
                current = []
                current_width = 0
            lines.append(truncate_to_fit(word, max_width_pt))
            continue
        if current and current_width + space_w + w > max_width_pt:
            lines.append(" ".join(current))
            current = [word]
            current_width = w
        else:
            if current:
                current_width += space_w + w
            else:
                current_width = w
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _get_pack_off_table_layout(page):
    """Detect Pack off table position on page 2 from template. Returns dict with start_y, row_height_pt, cols [(left, right), ...] for Packaging, Lot, Qty; or None."""
    try:
        blocks = page.get_text("dict").get("blocks", [])
        pack_header_y = None
        col_packaging = col_lot = col_qty = None
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip().lower()
                    bbox = span.get("bbox")
                    if not bbox or len(bbox) < 4:
                        continue
                    x0, y0, x1, y1 = bbox
                    if "pack off" in t or "packaging" in t or "lot" in t or ("quan" in t and "ty" in t):
                        pack_header_y = max(pack_header_y or 0, y1)
                    if "packaging" in t:
                        col_packaging = x0
                    if t == "lot":
                        col_lot = x0
                    if "quan" in t and "ty" in t and "pick" not in t:
                        col_qty = x0
        if pack_header_y is None or not all([col_packaging is not None, col_lot is not None, col_qty is not None]):
            return None
        # Next column right edges: use next column left or page width
        # From analyzer: Packaging 41.6, Lot 132.6, Qty 223.7; next is Pick Initial ~314.6
        try:
            pick_initial_x = None
            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        t = (span.get("text") or "").strip().lower()
                        bbox = span.get("bbox")
                        if bbox and "pick" in t and ("initial" in t or "ini" in t) and "pack" not in t:
                            pick_initial_x = bbox[0]
                            break
        except Exception:
            pick_initial_x = None
        right_qty = pick_initial_x if pick_initial_x is not None else (col_qty + 91)
        cols = [
            (float(col_packaging), float(col_lot)),
            (float(col_lot), float(col_qty)),
            (float(col_qty), float(right_qty)),
        ]
        # First data row: template has "(Indirect materials)" at y~493.6, first row ~506. Cap so we don't draw below visible table.
        start_y = pack_header_y + 14
        if start_y < 500:
            start_y = 506.0  # ensure we hit the first visible data row
        row_height_pt = 18
        return {"start_y": start_y, "row_height_pt": row_height_pt, "cols": cols}
    except Exception:
        return None


def _find_indirect_materials_section_y(page):
    """Find 'Indirect Materials' or 'Indirect' (e.g. under Packaging in pack off table); return y for first data row below it, or None."""
    try:
        blocks = page.get_text("dict").get("blocks", [])
        # 1) Scan every span for "indirect" (handles split text / encoding)
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip().lower()
                    if "indirect" in t:
                        bbox = span.get("bbox")
                        if bbox and len(bbox) >= 4:
                            return bbox[3] + 14
        # 2) Line-level: combine spans in case "Indirect" and "materials" are separate
        for block in blocks:
            for line in block.get("lines", []):
                line_text = ""
                line_y1 = None
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip()
                    bbox = span.get("bbox")
                    if bbox and len(bbox) >= 4:
                        line_y1 = bbox[3] if line_y1 is None else max(line_y1, bbox[3])
                    line_text += " " + t
                line_text = line_text.strip().lower()
                if "indirect" in line_text and line_y1 is not None:
                    return line_y1 + 14
        return None
    except Exception:
        return None


def _get_pick_list_column_xs(page):
    """Detect pick list column x positions from template headers so Quantity shows qty, not vendor."""
    try:
        blocks = page.get_text("dict").get("blocks", [])
        header_y = None
        xs = {}
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").lower()
                    bbox = span.get("bbox")
                    if not bbox or len(bbox) < 4:
                        continue
                    if "raw material" in t or "pick list" in t:
                        header_y = max(header_y or 0, bbox[3])
                        if "raw material" in t:
                            xs["raw_material"] = bbox[0]
                    if ("quantity" in t or t.strip() == "qty") and "pick" not in t:
                        xs["qty"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "vendor" in t and "lot" not in t and "wildwood" not in t:
                        xs["vendor"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "sku" in t:
                        xs["sku"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "vendor lot" in t or "vendor lot /" in t:
                        xs["vendor_lot"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "wildwood lot" in t:
                        if "vendor_lot" not in xs:
                            xs["vendor_lot"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "pick initial" in t or "pick initials" in t:
                        xs["pick_init"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
                    if "production initial" in t or "production initials" in t:
                        xs["prod_init"] = bbox[0]
                        header_y = max(header_y or 0, bbox[3])
        if not header_y or not xs:
            return None, None
        # 7 columns: raw_material, sku, vendor, vendor_lot (combined), qty, pick_init, prod_init
        order = ("raw_material", "sku", "vendor", "vendor_lot", "qty", "pick_init", "prod_init")
        col_list = []
        for k in order:
            if k in xs:
                col_list.append(xs[k])
            else:
                col_list.append(col_list[-1] + 50 if col_list else 43)
        start_y = header_y + 22
        return col_list, start_y
    except Exception:
        return None, None


def _fill_batch_ticket_template_pymupdf(
    template_pdf_path,
    fg,
    batch_number,
    quantity_produced_display,
    base_unit,
    pack_size_str,
    prod_date_str,
    pick_rows,
    pack_rows,
    indirect_materials_rows=None,
    qc_info=None,
    yield_val=None,
    loss_val=None,
    spill_val=None,
    waste_val=None,
    logo_path=None,
):
    if indirect_materials_rows is None:
        indirect_materials_rows = []
    if qc_info is None:
        qc_info = {}
    """
    Open the template PDF and insert variable data at positions found from the template text.
    Returns PDF bytes so the output is an exact copy of the template with data filled in.
    Returns None if PyMuPDF is missing or filling fails.

    Canonical version: Task 1 (template logo only, no white box/second logo); Task 2 (header
    layout, batch number redaction, Pack Size on own line, Calibri 10 + bold "Pack Size:"); Task 3
    (pick list: raw material column, combined Vendor Lot/Wildwood Lot, centered in cells).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        import fitz
        doc = fitz.open(template_pdf_path)
        num_pages = len(doc)
        if num_pages < 1:
            doc.close()
            return None
        # Task 1: use only the template's logo. Do not insert our logo or draw any white box.
        fontname = "helv"
        fontsize = 10
        color = (0, 0, 0)
        # Spacing: place value 8 pt right of label to avoid overlap
        label_value_gap = 8
        # Format batch size: show as integer when effectively whole (e.g. 700.01 -> 700)
        q = quantity_produced_display
        if abs(q - round(q)) <= 0.02:
            batch_size_str = f"{int(round(q))} {base_unit}"
        else:
            batch_size_str = f"{q:.2f} {base_unit}"
        batch_size_str = batch_size_str[:20]

        def insert_after(page, label, value, max_len=40):
            if not value:
                return
            pos = _find_text_bbox(page, label)
            if pos:
                x, y, fs = pos
                x = x + label_value_gap
                page.insert_text(
                    (x, y + fs * 0.8),
                    str(value)[:max_len],
                    fontsize=min(fs, 10),
                    fontname=fontname,
                    color=color,
                )

        # Fixed footer: redact body confidentiality first, then draw footer on every page
        for pnum in range(num_pages):
            _redact_confidentiality_from_body(doc[pnum])
            _draw_fixed_footer_confidentiality(doc[pnum], fontname=fontname, page_num=pnum + 1)
        if num_pages < 2:
            doc.new_page(width=612, height=792)
            _draw_fixed_footer_confidentiality(doc[1], fontname=fontname, page_num=2)

        # Redact template placeholder "BT-YYMMDD-Seq" on both pages so actual batch number replaces it
        _redact_batch_number_placeholder(doc[0])
        _redact_batch_number_placeholder(doc[1])
        # Redact "Pack Size:" when on same line as Batch Size so it doesn't overlap "700.00 lbs"
        _redact_pack_size_label_on_batch_size_line(doc[0])
        _redact_pack_size_label_on_batch_size_line(doc[1])

        # Logo: use only the template's logo (do not draw a white box or insert a second logo)

        # Page 1: header (fixed layout so Batch Number and Batch Size lines don't overlap)
        page0 = doc[0]
        layout = _get_header_layout(page0)
        if layout:
            vy = lambda y: y + layout["fs"] * 0.8
            page0.insert_text((layout["value_x"], vy(layout["y_product_id"])), str(fg.id)[:20], fontsize=min(layout["fs"], 10), fontname=fontname, color=color)
            page0.insert_text((layout["value_x"], vy(layout["y_sku"])), (fg.sku or "")[:30], fontsize=min(layout["fs"], 10), fontname=fontname, color=color)
            page0.insert_text((layout["value_x"], vy(layout["y_batch_number"])), (batch_number or "")[:24], fontsize=min(layout["fs"], 10), fontname=fontname, color=color)
            # Batch Size on line 1; Pack Size on line 2 — use template header font so Pack Size matches lines above
            page0.insert_text((layout["batch_size_x"], vy(layout["y_batch_size"])), batch_size_str, fontsize=min(layout["fs"], 10), fontname=fontname, color=color)
            _draw_pack_size_line(page0, layout["header_left_x"], vy(layout["y_pack_size"]), pack_size_str, color)
        else:
            insert_after(page0, "Product ID:", str(fg.id), 20)
            insert_after(page0, "SKU:", (fg.sku or "")[:30], 30)
            insert_after(page0, "Batch Number:", (batch_number or "")[:24], 24)
            header_pos = _find_header_column_xs(page0)
            if header_pos:
                y_bs = header_pos["batch_size_y"] + header_pos["fs"] * 0.8
                y_ps = header_pos["pack_size_y"] + header_pos["fs"] * 0.8
                page0.insert_text((header_pos["batch_size_x"], y_bs), batch_size_str, fontsize=min(header_pos["fs"], 10), fontname=fontname, color=color)
                page0.insert_text((header_pos["pack_size_x"], y_ps), (pack_size_str or "")[:20], fontsize=min(header_pos["fs"], 10), fontname=fontname, color=color)
            else:
                insert_after(page0, "Batch Size:", batch_size_str, 20)
                insert_after(page0, "Pack Size:", (pack_size_str or "")[:20], 20)
        insert_after(page0, "Production Date:", (prod_date_str or "")[:16], 16)

        # Pick list: use measured template positions; draw each cell with insert_text (insert_textbox hides text on this template)
        # 7 columns: raw_material, sku, vendor, vendor_lot (combined), qty, pick_init, prod_init
        try:
            pick_fontsize = 8
            row_height_pt = _P1_PICK_ROW_HEIGHT_PT
            _pick_col_widths = (57, 76, 57, 56, 46, 47, 50)
            pick_col_xs = list(_P1_PICK_COLS_PT)
            pick_start_y = _P1_PICK_FIRST_ROW_TOP_PT

            pick_col_right = []
            for j in range(7):
                if j < 6:
                    pick_col_right.append(float(pick_col_xs[j + 1]))
                else:
                    pick_col_right.append(float(pick_col_xs[j]) + _pick_col_widths[j])

            try:
                pick_font = fitz.Font(fontname)
            except Exception:
                pick_font = fitz.Font("helv")
            row_tops_pt = _P1_PICK_ROW_TOPS_PT
            for i, row in enumerate(pick_rows[:15]):
                if i < len(row_tops_pt):
                    y_top = row_tops_pt[i]
                    row_h = (row_tops_pt[i + 1] - row_tops_pt[i]) if (i + 1) < len(row_tops_pt) else _P1_PICK_ROW_HEIGHT_PT
                else:
                    y_top = pick_start_y + i * row_height_pt
                    row_h = row_height_pt
                cell_center_y = y_top + row_h / 2.0
                # insert_text point = bottom-left of first char; place so text sits roughly in cell (small offset from center)
                baseline_y = cell_center_y + pick_fontsize * 0.35
                vl = (row.get("vendor_lot") or "").strip()
                wl = (row.get("wildwood_lot") or "").strip()
                combined_lot = (vl + (" / " + wl if wl else ""))[:20]

                def _cell(s, max_len=24):
                    return (s or "").replace("\n", " ").replace("\r", "").strip()[:max_len]
                qty_val = _cell(row.get("qty"), 8)
                qty_with_uom = f"{qty_val} {base_unit}".strip() if qty_val else ""
                cells = [
                    _cell(row.get("raw_material"), 48),
                    _cell(row.get("sku"), 16),
                    _cell(row.get("vendor"), 12),
                    _cell(combined_lot, 20),
                    qty_with_uom,
                    _cell(row.get("pick_init"), 6),
                    _cell(row.get("prod_init"), 6),
                ]
                line_height_pt = pick_fontsize * 1.25
                cell_pad_pt = 2.0
                for j in range(7):
                    if j >= len(pick_col_xs) or j >= len(pick_col_right):
                        break
                    text = cells[j] if j < len(cells) else ""
                    if not text:
                        continue
                    try:
                        cell_left = float(pick_col_xs[j])
                        cell_right = pick_col_right[j]
                        cell_width_pt = max(1, cell_right - cell_left - cell_pad_pt * 2)
                        lines = _wrap_text_to_width(pick_font, text, pick_fontsize, cell_width_pt)
                        if not lines:
                            continue
                        max_lines = max(1, int(row_h / line_height_pt))
                        lines = lines[:max_lines]
                        n_lines = len(lines)
                        start_baseline_y = baseline_y - (n_lines - 1) * line_height_pt / 2.0
                        for line_idx, line in enumerate(lines):
                            if not line:
                                continue
                            text_width = pick_font.text_length(line, fontsize=pick_fontsize)
                            if text_width > cell_width_pt:
                                while line and pick_font.text_length(line + "…", fontsize=pick_fontsize) > cell_width_pt:
                                    line = line[:-1]
                                line = (line + "…") if line else ""
                            if not line:
                                continue
                            line_y = start_baseline_y + line_idx * line_height_pt
                            if line_y + pick_fontsize > y_top + row_h - 2:
                                continue
                            text_width = pick_font.text_length(line, fontsize=pick_fontsize)
                            if text_width > cell_width_pt:
                                continue
                            center_x = (cell_left + cell_right) / 2.0
                            x = center_x - text_width / 2.0
                            x = max(cell_left + cell_pad_pt, min(x, cell_right - cell_pad_pt - text_width))
                            page0.insert_text((x, line_y), line, fontsize=pick_fontsize, fontname=fontname, color=color)
                    except Exception as cell_err:
                        logger.warning("Pick list cell (%d,%d) failed: %s", i, j, cell_err)
        except Exception as pick_err:
            logger.warning("Pick list block failed (template fill continues): %s", pick_err)

        # Page 2: header (same fixed layout as page 1)
        page1 = doc[1]
        layout_p2 = _get_header_layout(page1)
        if layout_p2:
            vy = lambda y: y + layout_p2["fs"] * 0.8
            page1.insert_text((layout_p2["value_x"], vy(layout_p2["y_product_id"])), str(fg.id)[:20], fontsize=min(layout_p2["fs"], 10), fontname=fontname, color=color)
            page1.insert_text((layout_p2["value_x"], vy(layout_p2["y_sku"])), (fg.sku or "")[:30], fontsize=min(layout_p2["fs"], 10), fontname=fontname, color=color)
            page1.insert_text((layout_p2["value_x"], vy(layout_p2["y_batch_number"])), (batch_number or "")[:24], fontsize=min(layout_p2["fs"], 10), fontname=fontname, color=color)
            page1.insert_text((layout_p2["batch_size_x"], vy(layout_p2["y_batch_size"])), batch_size_str, fontsize=min(layout_p2["fs"], 10), fontname=fontname, color=color)
            _draw_pack_size_line(page1, layout_p2["header_left_x"], vy(layout_p2["y_pack_size"]), pack_size_str, color)
        else:
            insert_after(page1, "Product ID:", str(fg.id), 20)
            insert_after(page1, "SKU:", (fg.sku or "")[:30], 30)
            insert_after(page1, "Batch Number:", (batch_number or "")[:24], 24)
            header_pos_p2 = _find_header_column_xs(page1)
            if header_pos_p2:
                y_bs = header_pos_p2["batch_size_y"] + header_pos_p2["fs"] * 0.8
                y_ps = header_pos_p2["pack_size_y"] + header_pos_p2["fs"] * 0.8
                page1.insert_text((header_pos_p2["batch_size_x"], y_bs), batch_size_str, fontsize=min(header_pos_p2["fs"], 10), fontname=fontname, color=color)
                page1.insert_text((header_pos_p2["pack_size_x"], y_ps), (pack_size_str or "")[:20], fontsize=min(header_pos_p2["fs"], 10), fontname=fontname, color=color)
            else:
                insert_after(page1, "Batch Size:", batch_size_str, 20)
                insert_after(page1, "Pack Size:", (pack_size_str or "")[:20], 20)
        # Pack off table: use fixed first data row y=506 to match template (header ends ~493, first row at 506)
        pack_layout = _get_pack_off_table_layout(page1)
        if pack_layout:
            pack_row_height = pack_layout["row_height_pt"]
            pack_cols = pack_layout["cols"]
            start_y = 506.0  # force first data row so content appears in the visible table
        else:
            start_y = 506.0
            pack_row_height = 18
            pack_cols = [(41.6, 132.6), (132.6, 223.7), (223.7, 314.6)]  # Packaging, Lot, Qty from template page 2
        pack_fontsize = 8
        pack_pad_pt = 2.0
        try:
            pack_font = fitz.Font(fontname)
        except Exception:
            pack_font = fitz.Font("helv")
        pack_baseline_offset = pack_fontsize * 0.35

        # Build one list: indirect first, then outputs. Always draw at start_y (first data row of pack off table).
        all_pack_rows = []
        for r in (indirect_materials_rows or [])[:10]:
            qty = (r.get("qty") or "").strip()
            qty_display = f"{qty} EA".strip() if qty else ""
            all_pack_rows.append([
                (r.get("packaging") or "").strip(),
                (r.get("lot") or "").strip(),
                qty_display,
            ])
        for r in pack_rows[:10]:
            qty = (r.get("qty") or "").strip()
            qty_display = f"{qty} {base_unit}".strip() if qty else ""
            all_pack_rows.append([
                (r.get("packaging") or "").strip(),
                (r.get("lot") or "").strip(),
                qty_display,
            ])

        # Pack off: draw text in each cell. Baseline at cell bottom so text is visible (insert_text y = baseline).
        n_indirect = len(indirect_materials_rows or [])
        if all_pack_rows:
            print("[Batch ticket] Pack off: drawing %s row(s) (indirect=%s) at start_y=%s" % (len(all_pack_rows), n_indirect, start_y))
        line_h = pack_fontsize * 1.25
        def _draw_pack_off_rows(rows_data, base_y):
            for i, row_cells in enumerate(rows_data[:15]):
                y_top = base_y + i * pack_row_height
                cell_bottom = y_top + pack_row_height - 2
                for col_idx, (c_left, c_right) in enumerate(pack_cols):
                    if col_idx >= 3:
                        break
                    text = (row_cells[col_idx] if col_idx < len(row_cells) else "").strip()
                    if not text:
                        continue
                    cell_w = max(1, c_right - c_left - pack_pad_pt * 2)
                    lines = _wrap_text_to_width(pack_font, text, pack_fontsize, cell_w)
                    if not lines:
                        continue
                    max_lines = max(1, int(pack_row_height / line_h))
                    lines = lines[:max_lines]
                    for line_idx, line in enumerate(lines):
                        if not line:
                            continue
                        baseline_y = cell_bottom - 1 - (len(lines) - 1 - line_idx) * line_h
                        text_width = pack_font.text_length(line, fontsize=pack_fontsize)
                        if text_width > cell_w:
                            continue
                        center_x = (c_left + c_right) / 2.0
                        x = center_x - text_width / 2.0
                        x = max(c_left + pack_pad_pt, min(x, c_right - pack_pad_pt - text_width))
                        try:
                            page1.insert_text((x, baseline_y), line, fontsize=pack_fontsize, fontname=fontname, color=color)
                        except Exception as draw_err:
                            logger.warning("Pack off cell (%s,%s) draw failed: %s", i, col_idx, draw_err)
        _draw_pack_off_rows(all_pack_rows, start_y + 7)
        if yield_val:
            insert_after(page1, "Yield:", yield_val[:20], 20)
        if loss_val:
            insert_after(page1, "Loss:", loss_val[:20], 20)
        if spill_val:
            insert_after(page1, "Spill", spill_val[:12], 12)
        if waste_val:
            insert_after(page1, "Waste", waste_val[:12], 12)
        if qc_info.get("actual"):
            insert_after(page1, "QC", (qc_info.get("actual") or "")[:50], 50)

        out = BytesIO()
        doc.save(out, garbage=4, deflate=True)
        doc.close()
        return out.getvalue()
    except Exception as e:
        logger.exception("Batch ticket template fill failed, fallback PDF will be used: %s", e)
        return None


def _merge_template_first_page(template_path: str, content_pdf_bytes: bytes) -> bytes:
    """Prepend the template PDF's first page to the generated content. Returns merged PDF bytes."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return content_pdf_bytes

    try:
        reader_tpl = PdfReader(template_path)
        reader_content = PdfReader(BytesIO(content_pdf_bytes))
        writer = PdfWriter()
        if len(reader_tpl.pages) >= 1:
            writer.add_page(reader_tpl.pages[0])
        for page in reader_content.pages:
            writer.add_page(page)
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return content_pdf_bytes


def _cleanup_temp_dir(temp_dir):
    """Remove a temporary directory and its contents."""
    if not temp_dir or not os.path.isdir(temp_dir):
        return
    try:
        for f in Path(temp_dir).glob('*'):
            f.unlink()
        os.rmdir(temp_dir)
    except Exception:
        pass


# Letter size in points (ReportLab: origin bottom-left, 72 pt = 1 inch)
_LETTER_W = 612
_LETTER_H = 792

# Template overlay positions (inches from left, inches from bottom) — match Batch Ticket template.pdf layout
# Page 1: header block has labels left, we draw values to the right of each label
_P1_PRODUCT_ID = (1.5, 10.35)
_P1_SKU = (1.0, 10.1)
_P1_BATCH_NUMBER = (1.65, 9.85)
_P1_BATCH_SIZE = (1.5, 9.6)
_P1_PACK_SIZE = (4.0, 9.6)
_P1_PROD_DATE = (1.5, 7.25)
# Pick list table: first data row y, then row height; column x positions (inch)
_P1_PICK_Y_START = 4.35
_P1_PICK_ROW_HEIGHT = 0.2
# Pick list from actual "Batch ticket template.pdf" (analyze_batch_template.py)
# Column left edges (pt): Raw Material, SKU, Vendor, Vendor Lot, Qty, Pick Initials, Production Initials
_P1_PICK_COLS_PT = (41.6, 118.7, 195.6, 272.6, 350.8, 427.7, 504.6)
_P1_PICK_COLS = tuple(x / 72 for x in _P1_PICK_COLS_PT)  # inches for ReportLab
# Row positions from revised template horizontal lines (y from top). First row 171-208, then 208-254, 254-300, ...
_P1_PICK_ROW_TOPS_PT = (171.0, 208.0, 253.9, 299.9, 345.8, 391.9)
_P1_PICK_FIRST_ROW_TOP_PT = _P1_PICK_ROW_TOPS_PT[0]
_P1_PICK_ROW_HEIGHT_PT = 37.0  # fallback when row index >= len(row_tops)
_P1_PAGE_NUM_Y = 0.5
# Logo: top-left of page 1
_P1_LOGO_X, _P1_LOGO_Y = 0.5, 10.5
_P1_LOGO_W, _P1_LOGO_H = 2.0, 0.75


def _draw_overlay_page1(c, fg, batch_number, quantity_produced_display, base_unit, pack_size_str, prod_date_str, pick_rows, logo_path):
    """Draw overlay for template page 1: variable data only. No background so template shows through."""
    from reportlab.lib.units import inch
    c.setFont('Helvetica', 10)
    c.setFillColorRGB(0, 0, 0)
    # Logo (template may have placeholder at top-left)
    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, _P1_LOGO_X * inch, (_P1_LOGO_Y - _P1_LOGO_H) * inch, width=_P1_LOGO_W * inch, height=_P1_LOGO_H * inch, preserveAspectRatio=True)
        except Exception:
            pass
    # Header: one value per line to match template "Product ID:", "SKU:", "Batch Number:", "Batch Size:", "Pack Size:"
    c.drawString(_P1_PRODUCT_ID[0] * inch, _P1_PRODUCT_ID[1] * inch, str(fg.id))
    c.drawString(_P1_SKU[0] * inch, _P1_SKU[1] * inch, (fg.sku or '')[:30])
    c.drawString(_P1_BATCH_NUMBER[0] * inch, _P1_BATCH_NUMBER[1] * inch, (batch_number or '')[:24])
    c.drawString(_P1_BATCH_SIZE[0] * inch, _P1_BATCH_SIZE[1] * inch, f"{quantity_produced_display:.2f} {base_unit}"[:20])
    c.drawString(_P1_PACK_SIZE[0] * inch, _P1_PACK_SIZE[1] * inch, (pack_size_str or '')[:20])
    # Production Date (value on line below "Production Date:")
    c.drawString(_P1_PROD_DATE[0] * inch, _P1_PROD_DATE[1] * inch, (prod_date_str or '')[:16])
    # Pick list table rows (template has headers; we draw data only)
    row_y = _P1_PICK_Y_START
    cols = _P1_PICK_COLS
    c.setFont('Helvetica', 9)
    for row in pick_rows:
        c.drawString(cols[0] * inch, row_y * inch, (row.get('sku') or '')[:18])
        c.drawString(cols[1] * inch, row_y * inch, (row.get('vendor') or '')[:14])
        c.drawString(cols[2] * inch, row_y * inch, (row.get('vendor_lot') or '')[:12])
        c.drawString(cols[3] * inch, row_y * inch, (row.get('qty') or '')[:8])
        c.drawString(cols[4] * inch, row_y * inch, (row.get('pick_init') or '')[:6])
        c.drawString(cols[5] * inch, row_y * inch, (row.get('prod_init') or '')[:6])
        c.drawString(cols[6] * inch, row_y * inch, (row.get('wildwood_lot') or '')[:14])
        row_y -= _P1_PICK_ROW_HEIGHT
    c.setFont('Helvetica', 9)
    c.drawCentredString(_LETTER_W / 2, _P1_PAGE_NUM_Y * inch, '-- 1 of 2 --')


# Page 2 overlay positions (match template)
_P2_PRODUCT_ID = (1.5, 10.35)
_P2_SKU = (1.0, 10.1)
_P2_BATCH_NUMBER = (1.65, 9.85)
_P2_BATCH_SIZE = (1.5, 9.6)
_P2_PACK_SIZE = (4.0, 9.6)
_P2_PACK_TABLE_Y_START = 6.0
_P2_PACK_ROW_HEIGHT = 0.22
_P2_PACK_COLS = (0.6, 1.7, 2.4, 3.15, 3.85, 4.6)  # Packaging, Lot, Qty, Pick Initial, Pack Initial, Amount Unused
_P2_YIELD_LOSS_Y = 4.25
_P2_YIELD_X, _P2_LOSS_X, _P2_ENDTIME_X = 1.0, 2.3, 4.0
_P2_SPILL_WASTE_Y = 4.0
_P2_SPILL_X, _P2_WASTE_X = 1.0, 2.8
_P2_QC_Y = 2.0
_P2_PAGE_NUM_Y = 0.5


def _draw_overlay_page2(c, fg, batch_number, quantity_produced_display, base_unit, pack_size_str, pack_rows, qc_info, yield_val, loss_val, spill_val, waste_val):
    """Draw overlay for template page 2: variable data only. No background so template shows through."""
    from reportlab.lib.units import inch
    c.setFont('Helvetica', 10)
    c.setFillColorRGB(0, 0, 0)
    # Header (same layout as page 1)
    c.drawString(_P2_PRODUCT_ID[0] * inch, _P2_PRODUCT_ID[1] * inch, str(fg.id))
    c.drawString(_P2_SKU[0] * inch, _P2_SKU[1] * inch, (fg.sku or '')[:30])
    c.drawString(_P2_BATCH_NUMBER[0] * inch, _P2_BATCH_NUMBER[1] * inch, (batch_number or '')[:24])
    c.drawString(_P2_BATCH_SIZE[0] * inch, _P2_BATCH_SIZE[1] * inch, f"{quantity_produced_display:.2f} {base_unit}"[:20])
    c.drawString(_P2_PACK_SIZE[0] * inch, _P2_PACK_SIZE[1] * inch, (pack_size_str or '')[:20])
    # Pack Off table data rows
    row_y = _P2_PACK_TABLE_Y_START
    cols = _P2_PACK_COLS
    c.setFont('Helvetica', 9)
    for row in pack_rows:
        c.drawString(cols[0] * inch, row_y * inch, (row.get('packaging') or '')[:20])
        c.drawString(cols[1] * inch, row_y * inch, (row.get('lot') or '')[:14])
        c.drawString(cols[2] * inch, row_y * inch, (row.get('qty') or '')[:8])
        row_y -= _P2_PACK_ROW_HEIGHT
    c.setFont('Helvetica', 10)
    # Yield, Loss, End Time line
    if yield_val:
        c.drawString(_P2_YIELD_X * inch, _P2_YIELD_LOSS_Y * inch, yield_val[:20])
    if loss_val:
        c.drawString(_P2_LOSS_X * inch, _P2_YIELD_LOSS_Y * inch, loss_val[:20])
    # Spill, Waste
    if spill_val:
        c.drawString(_P2_SPILL_X * inch, _P2_SPILL_WASTE_Y * inch, spill_val[:12])
    if waste_val:
        c.drawString(_P2_WASTE_X * inch, _P2_SPILL_WASTE_Y * inch, waste_val[:12])
    # QC data
    if qc_info.get('actual'):
        c.drawString(1.0 * inch, _P2_QC_Y * inch, (qc_info['actual'] or '')[:50])
    if qc_info.get('initials'):
        c.drawString(1.0 * inch, (_P2_QC_Y - 0.25) * inch, (qc_info['initials'] or '')[:20])
    c.setFont('Helvetica', 9)
    c.drawCentredString(_LETTER_W / 2, _P2_PAGE_NUM_Y * inch, '-- 2 of 2 --')


def _build_overlay_pdf(pick_rows, pack_rows, fg, batch_number, quantity_produced_display, base_unit, pack_size_str, prod_date_str, qc_info, yield_val, loss_val, spill_val, waste_val, logo_path):
    """Build 2-page overlay PDF (data only) for merging on top of template."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _draw_overlay_page1(c, fg, batch_number, quantity_produced_display, base_unit, pack_size_str, prod_date_str, pick_rows, logo_path)
    c.showPage()
    _draw_overlay_page2(c, fg, batch_number, quantity_produced_display, base_unit, pack_size_str, pack_rows, qc_info, yield_val, loss_val, spill_val, waste_val)
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _merge_overlay_onto_template(template_pdf_path, overlay_pdf_bytes):
    """Merge overlay PDF (our data) on top of template PDF (design). Returns merged PDF bytes."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return None
    try:
        reader_tpl = PdfReader(template_pdf_path)
        reader_ov = PdfReader(BytesIO(overlay_pdf_bytes))
        writer = PdfWriter()
        for i in range(max(len(reader_tpl.pages), len(reader_ov.pages))):
            if i < len(reader_tpl.pages):
                page = reader_tpl.pages[i]
                if i < len(reader_ov.pages):
                    page.merge_page(reader_ov.pages[i], over=True)
                writer.add_page(page)
            else:
                writer.add_page(reader_ov.pages[i])
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return None


def build_batch_ticket_pdf(batch):
    """
    Build the batch ticket PDF to match the BP-13 template design (Batch Ticket template).
    Two-page layout: Page 1 = header, production date, pre-prod checks, pick list (raw materials);
    Page 2 = post-prod checks, pack off (outputs), yield/loss/spill/waste, signatures, QC.
    """
    import logging
    import re
    logger = logging.getLogger(__name__)

    if not getattr(batch, 'finished_good_item', None):
        raise ValueError('Batch has no finished good item; cannot generate batch ticket PDF.')

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
    except ImportError as e:
        raise ImportError('reportlab is required for batch ticket PDF. Install with: pip install reportlab') from e
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    fg = batch.finished_good_item
    base_unit = fg.unit_of_measure or 'lbs'

    def convert_from_lbs_to_base(quantity_in_lbs):
        if base_unit in ('lbs', 'ea'):
            return quantity_in_lbs
        if base_unit == 'kg':
            return quantity_in_lbs / 2.20462
        return quantity_in_lbs

    if batch.batch_type == 'repack':
        quantity_produced_display = batch.quantity_produced
    else:
        quantity_produced_display = convert_from_lbs_to_base(batch.quantity_produced)

    pack_size_str = ''
    if getattr(fg, 'pack_size', None) is not None:
        pack_size_str = f"{fg.pack_size} {base_unit}"
    elif fg.pack_sizes.filter(is_active=True).exists():
        ps = fg.pack_sizes.filter(is_active=True).first()
        pack_size_str = f"{ps.pack_size} {ps.pack_size_unit}"

    prod_date_str = batch.production_date.strftime('%m/%d/%Y') if batch.production_date else ''

    # Parse QC from notes
    qc_info = {}
    if batch.notes:
        for key, pattern in [
            ('parameters', r'QC Parameters:\s*(.+?)(?:\n|QC Actual:|$)'),
            ('actual', r'QC Actual:\s*(.+?)(?:\n|QC Initials:|$)'),
            ('initials', r'QC Initials:\s*(.+?)(?:\n|$)'),
        ]:
            m = re.search(pattern, batch.notes, re.IGNORECASE | re.DOTALL)
            if m:
                qc_info[key] = m.group(1).strip()

    status_prefix = batch.status.replace('_', '-')
    filename = f"{status_prefix}({batch.batch_number}).pdf"

    # Prefer: copy the template EXACTLY by filling it with our data (PyMuPDF)
    template_path = get_batch_ticket_template_path()
    if not template_path:
        logger.info(
            "Batch ticket template not found; using flowable PDF. "
            "For the canonical template design, add 'Batch Ticket template.pdf' (or .docx) to backend_django/batch_ticket_template/"
        )
    if template_path:
        pdf_path, temp_dir = _get_template_pdf_path(template_path)
        if pdf_path and Path(pdf_path).suffix.lower() == '.pdf':
            try:
                from .pdf_generator import get_logo_path
                logo_path = get_logo_path()
            except Exception:
                logo_path = None
            # Same relationship as pick list: one loop over batch.inputs. Raw -> pick list, indirect -> pack off.
            pick_rows = []
            indirect_materials_rows = []
            for batch_input in batch.inputs.select_related('lot__item').all():
                lot = batch_input.lot
                item = lot.item
                if _is_indirect_material(item):
                    qty_str = f"{int(batch_input.quantity_used)}" if batch_input.quantity_used == int(batch_input.quantity_used) else f"{batch_input.quantity_used:.2f}"
                    indirect_materials_rows.append({
                        'packaging': (getattr(item, 'description', None) or item.name or item.sku or '').strip(),
                        'lot': lot.lot_number or '—',
                        'qty': qty_str,
                        'uom': 'EA',
                    })
                    continue
                vendor = (getattr(item, 'vendor', None) or '').strip() or '—'
                vendor_lot = (lot.vendor_lot_number or lot.lot_number or '—').strip()
                qty = batch_input.quantity_used
                if (item.unit_of_measure or 'lbs') == 'kg':
                    qty = qty * 2.20462
                qty_base = convert_from_lbs_to_base(qty)
                qty_str = f"{int(round(qty_base))}" if abs(qty_base - round(qty_base)) <= 0.01 else f"{qty_base:.2f}"
                raw_material = (getattr(item, 'description', None) or item.name or item.sku or '').strip()
                uom = (getattr(item, 'unit_of_measure', None) or 'lbs').strip() or 'lbs'
                pick_rows.append({
                    'raw_material': raw_material,
                    'sku': item.sku,
                    'vendor': vendor,
                    'vendor_lot': vendor_lot,
                    'qty': qty_str,
                    'uom': uom,
                    'wildwood_lot': lot.lot_number or '',
                })
            pack_rows = []
            for batch_output in batch.outputs.select_related('lot__item').all():
                lot = batch_output.lot
                item = lot.item
                qty = batch_output.quantity_produced
                if batch.batch_type != 'repack':
                    qty = convert_from_lbs_to_base(qty)
                qty_str = f"{qty:.2f}" if qty != int(qty) else str(int(qty))
                packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
                pack_rows.append({'packaging': packaging_desc, 'lot': lot.lot_number, 'qty': qty_str})
            yield_val = ''
            if batch.status == 'closed' and getattr(batch, 'quantity_actual', None):
                yield_val = f"{convert_from_lbs_to_base(batch.quantity_actual):.2f} {base_unit}"
            loss_val = ''
            if batch.status == 'closed' and getattr(batch, 'variance', None) is not None:
                loss_val = f"{convert_from_lbs_to_base(batch.variance):.2f} {base_unit}"
            spill_val = f"{convert_from_lbs_to_base(batch.spills):.2f}" if getattr(batch, 'spills', None) else ''
            waste_val = f"{convert_from_lbs_to_base(batch.wastes):.2f}" if getattr(batch, 'wastes', None) else ''
            filled = _fill_batch_ticket_template_pymupdf(
                pdf_path,
                fg,
                batch.batch_number,
                quantity_produced_display,
                base_unit,
                pack_size_str,
                prod_date_str,
                pick_rows,
                pack_rows,
                indirect_materials_rows,
                qc_info,
                yield_val,
                loss_val,
                spill_val,
                waste_val,
                logo_path,
            )
            if temp_dir:
                _cleanup_temp_dir(temp_dir)
            if filled:
                return filled, filename
            logger.warning(
                "Batch ticket template fill failed (PyMuPDF); using flowable PDF. "
                "Ensure pymupdf is installed: pip install pymupdf"
            )
        if temp_dir:
            _cleanup_temp_dir(temp_dir)

    # Fallback: build PDF from flowables
    buffer = BytesIO()
    doc_title = f"{status_prefix.upper()}({batch.batch_number})"
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        title=doc_title,
        author="WWI ERP System",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'BatchTicketTitle',
        parent=styles['Heading1'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=0,
        alignment=TA_CENTER,
    )
    small_style = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.black,
        spaceAfter=3,
        spaceBefore=0,
        leading=9,
    )
    normal_style = ParagraphStyle(
        'NormalBT',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=3,
        spaceBefore=0,
    )

    elements = []
    space_sm = 0.1 * inch
    space_md = 0.15 * inch

    # Pick List table: fixed dimensions to match template (7 columns, total width 7.5")
    _PICK_TABLE_WIDTH = 7.5 * inch
    _PICK_COL_WIDTHS = (
        1.65 * inch,  # Raw Material SKU
        1.20 * inch,  # Vendor
        1.20 * inch,  # Vendor Lot
        0.55 * inch,  # Quantity
        0.75 * inch,  # Pick Initials
        0.95 * inch,  # Production Initials
        1.20 * inch,  # Wildwood Lot
    )  # sum = 7.5"
    _PICK_ROW_HEIGHT = 0.22 * inch  # fixed row height for header and data rows

    # Logo path: try pdf_generator, then batch_ticket_template, then Sensitive, then frontend/public
    def _batch_ticket_logo_path():
        try:
            from .pdf_generator import get_logo_path
            p = get_logo_path()
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
        base = Path(__file__).resolve().parent.parent.parent
        backend = Path(__file__).resolve().parent.parent
        for folder, names in [
            (backend / 'batch_ticket_template', ['logo.png', 'Logo.png', 'Wildwood Ingredients Logo - Transparent Background.png']),
            (base / 'Sensitive', ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']),
            (base / 'frontend' / 'public', ['logo.png']),
        ]:
            if folder.exists():
                for name in names:
                    path = folder / name
                    if path.exists():
                        return str(path)
        return None

    logo_path = _batch_ticket_logo_path()

    # ----- PAGE 1: Match template layout exactly -----
    # 1. HEADER: Logo (left) | Product ID, SKU, Batch Number, Batch Size, Pack Size (right)
    header_right_data = [
        ['Product ID:', str(fg.id)],
        ['SKU:', fg.sku or ''],
        ['Batch Number:', batch.batch_number or ''],
        ['Batch Size:', f"{int(round(quantity_produced_display))} {base_unit}" if abs(quantity_produced_display - round(quantity_produced_display)) <= 0.02 else f"{quantity_produced_display:.2f} {base_unit}"],
        ['Pack Size:', pack_size_str or ''],
    ]
    header_right_tbl = Table(header_right_data, colWidths=[0.9 * inch, 2.2 * inch])
    header_right_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    logo_cell = ''
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image(logo_path, width=2.0 * inch, height=0.7 * inch, preserveAspectRatio=True)
            logo_cell = logo_img
        except Exception:
            pass
    if not logo_cell:
        logo_cell = Paragraph('<i>Logo</i>', ParagraphStyle('LogoPlaceholder', parent=styles['Normal'], fontSize=8, textColor=colors.grey))
    header_tbl = Table([[logo_cell, header_right_tbl]], colWidths=[2.5 * inch, 3.5 * inch])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, space_sm))

    # 2. PICK LIST: heading, Pick Date line, then table — fixed dimensions to match template
    elements.append(Paragraph("Pick List", ParagraphStyle('BoldPick', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10)))
    elements.append(Spacer(1, 0.04 * inch))
    elements.append(Paragraph("Pick Date___________&nbsp;&nbsp;&nbsp;Start Time _________&nbsp;&nbsp;&nbsp;End Time___________", normal_style))
    elements.append(Spacer(1, 0.06 * inch))
    pick_headers = ['Raw Material SKU', 'Vendor', 'Vendor Lot', 'Quantity', 'Pick Initials', 'Production Initials', 'Wildwood Lot']
    pick_rows = [pick_headers]
    for batch_input in batch.inputs.select_related('lot__item').all():
        lot = batch_input.lot
        item = lot.item
        if _is_indirect_material(item):
            continue
        vendor = (getattr(item, 'vendor', None) or '').strip() or '—'
        vendor_lot = (lot.vendor_lot_number or lot.lot_number or '—').strip()
        qty = batch_input.quantity_used
        if (item.unit_of_measure or 'lbs') == 'kg':
            qty = qty * 2.20462
        qty_base = convert_from_lbs_to_base(qty)
        qty_str = f"{int(round(qty_base))}" if abs(qty_base - round(qty_base)) <= 0.01 else f"{qty_base:.2f}"
        pick_rows.append([item.sku or '', vendor[:14], vendor_lot[:12], qty_str, '', '', lot.lot_number or ''])
    if len(pick_rows) == 1:
        pick_rows.append(['', '', '', '', '', '', ''])
    pick_tbl = Table(pick_rows, colWidths=_PICK_COL_WIDTHS)
    pick_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(pick_tbl)
    elements.append(Spacer(1, space_sm))

    # 3. HORIZONTAL DIVIDING LINE
    line_tbl = Table([['']], colWidths=[7.5 * inch])
    line_tbl.setStyle(TableStyle([('LINEABOVE', (0, 0), (0, 0), 1, colors.black)]))
    elements.append(line_tbl)
    elements.append(Spacer(1, space_sm))

    # 4. Pre-Production Checks (left) | Start Time (right) — same line
    preprod_tbl = Table([['Pre-Production Checks', 'Start Time ____________']], colWidths=[4.0 * inch, 3.0 * inch])
    preprod_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(preprod_tbl)
    elements.append(Spacer(1, 0.06 * inch))

    # 5. Equipment and 20 mesh (template)
    precheck_data = [
        ['Equipment Sanitized and in good order?', 'Yes', 'No', 'Campaign', 'Operator Initials _________', 'Supervisor Initials _________'],
        ['Has 20 mesh screen been inspected and installed properly?', 'Yes', 'No', '', 'Operator Initials _________', 'Supervisor Initials _________'],
    ]
    precheck_tbl = Table(precheck_data, colWidths=[2.0 * inch, 0.35 * inch, 0.3 * inch, 0.55 * inch, 1.15 * inch, 1.2 * inch])
    precheck_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOX', (1, 0), (2, -1), 0.5, colors.grey),
        ('INNERGRID', (1, 0), (2, -1), 0.25, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(precheck_tbl)
    elements.append(Spacer(1, space_md))

    # 6. Batch Instructions (template)
    elements.append(Paragraph("Batch Instructions", ParagraphStyle('Bold2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)))
    elements.append(Spacer(1, 0.04 * inch))
    step_data = [['Step', 'Initial After Completion'], ['1.)', ''], ['2.)', ''], ['3.)', ''], ['4.)', ''], ['5.)', ''], ['6.)', 'End Time ____________']]
    step_tbl = Table(step_data, colWidths=[0.55 * inch, 4.0 * inch])
    step_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(step_tbl)
    elements.append(Spacer(1, space_md))

    # 7. Production Date (template)
    elements.append(Paragraph("Production Date:", normal_style))
    elements.append(Paragraph(prod_date_str if prod_date_str else "_________________", normal_style))
    elements.append(Spacer(1, space_sm))

    # 8. Confidentiality and footer (template)
    conf_para = (
        "This document contains confidential and proprietary information intended solely for the recipient. "
        "By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, "
        "distribute, or use any information herein for purposes other than those expressly authorized. "
        "Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, "
        "please notify the sender immediately and delete this document from your system."
    )
    elements.append(Paragraph(conf_para, small_style))
    elements.append(Paragraph(
        "Batch Ticket – Updated 02/06/2026 (GDM) – Reviewed by GM – Effective Date 02/06/2026 (BP-13)",
        small_style,
    ))
    elements.append(Spacer(1, space_sm))
    elements.append(Paragraph("-- 1 of 2 --", ParagraphStyle('PageNum', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)))

    # ---------- PAGE 2 (template order) ----------
    elements.append(PageBreak())
    # Line 1: Batch Ticket
    elements.append(Paragraph("Batch Ticket", title_style))
    elements.append(Spacer(1, space_sm))
    # Lines 2–5: Same header table as page 1
    elements.append(header_tbl)
    elements.append(Spacer(1, space_sm))
    # Lines 6–9: Confidentiality, footer
    elements.append(Paragraph(conf_para, small_style))
    elements.append(Paragraph("Batch Ticket – Updated 02/06/2026 (GDM) – Reviewed by GM – Effective Date 02/06/2026 (BP-13)", small_style))
    elements.append(Spacer(1, space_sm))
    # Line 10: Post-Production Checks 	Start Time ____________
    elements.append(Paragraph("Post-Production Checks&nbsp;&nbsp;&nbsp;&nbsp;Start Time ____________", ParagraphStyle('Bold4', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)))
    elements.append(Spacer(1, 0.05 * inch))
    # Line 11: Screen Clean of Extraneous Foreign Material?
    elements.append(Paragraph("Screen Clean of Extraneous Foreign Material?", normal_style))
    # Line 12: Yes 	No 	If No, Explain:________________________________________________________
    elements.append(Paragraph("Yes&nbsp;&nbsp;&nbsp;No&nbsp;&nbsp;&nbsp;If No, Explain:________________________________________________________", normal_style))
    # Line 13: Operator Initials _____________ Supervisor Initials _______________
    elements.append(Paragraph("Operator Initials _____________&nbsp;&nbsp;&nbsp;Supervisor Initials _______________", normal_style))
    elements.append(Spacer(1, space_md))
    # Line 14: Pack Off
    elements.append(Paragraph("Pack Off", ParagraphStyle('Bold5', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)))
    elements.append(Spacer(1, 0.05 * inch))
    # Line 15: Packaging 	Lot 	Quantity 	Pick Initial 	Pack Initial 	Amount Unused & Returned to Inventory
    pack_headers = ['Packaging', 'Lot', 'Quantity', 'Pick Initial', 'Pack Initial', 'Amount Unused & Returned to Inventory']
    pack_rows = [pack_headers]
    # Same relationship as pick list: batch.inputs. Indirect -> pack off (first), then outputs.
    for batch_input in batch.inputs.select_related('lot__item').all():
        if not _is_indirect_material(batch_input.lot.item):
            continue
        item = batch_input.lot.item
        lot = batch_input.lot
        qty_str = f"{int(batch_input.quantity_used)}" if batch_input.quantity_used == int(batch_input.quantity_used) else f"{batch_input.quantity_used:.2f}"
        packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
        pack_rows.append([packaging_desc, lot.lot_number or '', f"{qty_str} EA", '', '', ''])
    for batch_output in batch.outputs.select_related('lot__item').all():
        lot = batch_output.lot
        item = lot.item
        qty = batch_output.quantity_produced
        if batch.batch_type != 'repack':
            qty = convert_from_lbs_to_base(qty)
        qty_str = f"{qty:.2f}" if qty != int(qty) else str(int(qty))
        packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
        pack_rows.append([packaging_desc, lot.lot_number or '', qty_str, '', '', ''])
    if len(pack_rows) == 1:
        pack_rows.append(['', '', '', '', '', ''])
    pack_tbl = Table(pack_rows, colWidths=[1.1 * inch, 0.9 * inch, 0.55 * inch, 0.7 * inch, 0.7 * inch, 1.5 * inch])
    pack_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(pack_tbl)
    elements.append(Spacer(1, space_sm))
    # Line 16: *Enter (+) when adding unused packaging back to inventory and a (-) when removing additional packaging.
    elements.append(Paragraph("*Enter (+) when adding unused packaging back to inventory and a (-) when removing additional packaging.", small_style))
    elements.append(Spacer(1, space_sm))
    # Line 17: Yield: ______________ 	Loss: _____________ 	End Time ____________
    yield_val = ''
    if batch.status == 'closed' and getattr(batch, 'quantity_actual', None):
        yield_val = f"{convert_from_lbs_to_base(batch.quantity_actual):.2f} {base_unit}"
    loss_val = ''
    if batch.status == 'closed' and getattr(batch, 'variance', None) is not None:
        loss_val = f"{convert_from_lbs_to_base(batch.variance):.2f} {base_unit}"
    elements.append(Paragraph(f"Yield: {yield_val or '_______________'}&nbsp;&nbsp;&nbsp;Loss: {loss_val or '_____________'}&nbsp;&nbsp;&nbsp;End Time ____________", normal_style))
    # Line 18: Spill 	Waste
    spill_val = f"{convert_from_lbs_to_base(batch.spills):.2f}" if getattr(batch, 'spills', None) else ''
    waste_val = f"{convert_from_lbs_to_base(batch.wastes):.2f}" if getattr(batch, 'wastes', None) else ''
    elements.append(Paragraph(f"Spill&nbsp;&nbsp;&nbsp;&nbsp;{spill_val}&nbsp;&nbsp;&nbsp;&nbsp;Waste&nbsp;&nbsp;&nbsp;&nbsp;{waste_val}", normal_style))
    elements.append(Spacer(1, space_md))
    # Lines 19–20: I confirm that all information recorded on this batch record...
    elements.append(Paragraph(
        "I confirm that all information recorded on this batch record is complete, accurate, and recorded in real time. "
        "I have followed all applicable batch instructions, food safety, GMP, and HACCP requirements for this production run, "
        "and I have reported any deviations, issues, or concerns immediately",
        small_style,
    ))
    elements.append(Spacer(1, space_sm))
    # Line 21: Production Signature 	Date
    elements.append(Paragraph("Production Signature&nbsp;&nbsp;&nbsp;&nbsp;Date", normal_style))
    # Line 22: ________________________ 	_________
    elements.append(Paragraph("________________________&nbsp;&nbsp;&nbsp;&nbsp;_________", normal_style))
    # Line 23: Supervisor Verification 	Date
    elements.append(Paragraph("Supervisor Verification&nbsp;&nbsp;&nbsp;&nbsp;Date", normal_style))
    # Line 24: ________________________ 	__________
    elements.append(Paragraph("________________________&nbsp;&nbsp;&nbsp;&nbsp;__________", normal_style))
    elements.append(Spacer(1, space_sm))
    # Line 25: QC Results (Please write all data): Start Time _________ Initials __________
    elements.append(Paragraph("QC Results (Please write all data): Start Time _________ Initials __________", normal_style))
    # Line 26: Adjustments (If needed):
    elements.append(Paragraph("Adjustments (If needed):", small_style))
    # Line 27: Raw Materials added as an adjustment should be repicked and highlighted
    elements.append(Paragraph("Raw Materials added as an adjustment should be repicked and highlighted", small_style))
    qc_disposition = ''
    if qc_info.get('actual'):
        qc_disposition = qc_info['actual']
    if qc_info.get('initials'):
        qc_disposition = (qc_disposition + '  Initials: ' + qc_info['initials']).strip()
    if qc_disposition:
        elements.append(Paragraph(f"QC Data: {qc_disposition}", normal_style))
    # Line 28: QC Disposition:
    elements.append(Paragraph("QC Disposition:", normal_style))
    # Line 29: Approve 	Not Approved
    elements.append(Paragraph("Approve&nbsp;&nbsp;&nbsp;&nbsp;Not Approved", normal_style))
    # Line 30: Initials: ________________
    elements.append(Paragraph("Initials: ________________", normal_style))
    # Line 31: If QC does not approve, please place on hold and notify supervisor End Time ____________
    elements.append(Paragraph("If QC does not approve, please place on hold and notify supervisor&nbsp;&nbsp;&nbsp;End Time ____________", small_style))
    elements.append(Spacer(1, space_sm))
    # Line 32: -- 2 of 2 --
    elements.append(Paragraph("-- 2 of 2 --", ParagraphStyle('PageNum2', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    # No longer prepend external template file; the layout above IS the BP-13 design
    return pdf_bytes, filename
