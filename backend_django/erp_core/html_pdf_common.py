"""
Shared HTML → PDF conversion using xhtml2pdf (pisa).

Default: **in-process** conversion (fast — no Windows multiprocessing spawn per request).

Optional: set ``HTML_PDF_USE_SUBPROCESS = True`` in Django settings (or env
``HTML_PDF_USE_SUBPROCESS=1``) to run each conversion in a child process with a
timeout (slower, but the worker can be killed if the renderer hangs).
"""
import logging
from io import BytesIO
from multiprocessing import Process, Queue

logger = logging.getLogger(__name__)

DEFAULT_XHTML2PDF_TIMEOUT = 120


def _xhtml2pdf_in_process(html_string: str, log_label: str) -> bytes | None:
    """Run xhtml2pdf in the current process (typical path — much faster on Windows)."""
    try:
        from xhtml2pdf import pisa

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        err = getattr(result, "err", 1)
        if err != 0:
            logger.warning("%s HTML→PDF: xhtml2pdf reported errors (%s)", log_label, err)
            return None
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.warning("%s HTML→PDF in-process failed: %s", log_label, e, exc_info=True)
        return None


def _xhtml2pdf_worker(html_string: str, out_queue: Queue) -> None:
    try:
        from xhtml2pdf import pisa

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        err = getattr(result, "err", 1)
        if err != 0:
            out_queue.put(("error", f"xhtml2pdf errors: {err}"))
            return
        pdf_buffer.seek(0)
        out_queue.put(("ok", pdf_buffer.getvalue()))
    except Exception as e:
        out_queue.put(("error", str(e)))


def _use_subprocess() -> bool:
    try:
        from django.conf import settings

        return bool(getattr(settings, "HTML_PDF_USE_SUBPROCESS", False))
    except Exception:
        return False


def html_string_to_pdf_bytes(
    html_string: str,
    *,
    timeout_seconds: int = DEFAULT_XHTML2PDF_TIMEOUT,
    log_label: str = "PDF",
) -> bytes | None:
    """
    Render HTML to PDF bytes. Returns None on failure or subprocess timeout.
    """
    if not html_string or not html_string.strip():
        logger.warning("%s HTML→PDF: empty HTML", log_label)
        return None

    if not _use_subprocess():
        return _xhtml2pdf_in_process(html_string, log_label)

    try:
        out_queue: Queue = Queue()
        proc = Process(target=_xhtml2pdf_worker, args=(html_string, out_queue), daemon=True)
        proc.start()
        proc.join(timeout_seconds)
        if proc.is_alive():
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(1)
            logger.warning(
                "%s HTML→PDF subprocess timed out after %ss",
                log_label,
                timeout_seconds,
            )
            return None
        if out_queue.empty():
            logger.warning("%s HTML→PDF: no data from worker", log_label)
            return None
        status, payload = out_queue.get()
        if status != "ok":
            logger.warning("%s HTML→PDF worker failed: %s", log_label, payload)
            return None
        return payload
    except Exception as e:
        logger.warning("%s HTML→PDF subprocess failed: %s", log_label, e, exc_info=True)
        return None
