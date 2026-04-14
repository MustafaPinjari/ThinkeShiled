"""
Celery tasks for the audit app.

Tasks
-----
generate_audit_pdf(date_from, date_to, requested_by_user_id)
    Generates a PDF report of all AuditLog entries within the given date
    range and stores it in MEDIA_ROOT/audit_exports/.  Must complete within
    30 seconds (Requirement 11.4).
"""

from __future__ import annotations

import io
import logging
import os
from datetime import date, datetime, timezone as dt_timezone

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Directory where generated PDFs are stored
EXPORT_DIR_NAME = "audit_exports"


def _get_export_dir() -> str:
    """Return (and create if necessary) the directory for audit PDF exports."""
    media_root = getattr(settings, "MEDIA_ROOT", None) or os.path.join(
        settings.BASE_DIR, "media"
    )
    export_dir = os.path.join(media_root, EXPORT_DIR_NAME)
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


@shared_task(bind=True, time_limit=30, soft_time_limit=25, name="audit.generate_audit_pdf")
def generate_audit_pdf(self, date_from: str, date_to: str, requested_by_user_id=None):
    """
    Generate a PDF report of AuditLog entries for the given date range.

    Parameters
    ----------
    date_from:              ISO date string "YYYY-MM-DD" (inclusive).
    date_to:                ISO date string "YYYY-MM-DD" (inclusive).
    requested_by_user_id:   PK of the User who requested the export (for
                            the AuditLog entry written on completion).

    Returns a dict:
        {
            "status": "completed",
            "file_path": "<relative path under MEDIA_ROOT>",
            "entry_count": <int>,
        }
    """
    from audit.models import AuditLog, EventType
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # ------------------------------------------------------------------ #
    # 1. Parse date range                                                  #
    # ------------------------------------------------------------------ #
    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(
            tzinfo=dt_timezone.utc
        )
        dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=dt_timezone.utc
        )
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {exc}") from exc

    # ------------------------------------------------------------------ #
    # 2. Query AuditLog entries                                            #
    # ------------------------------------------------------------------ #
    entries = list(
        AuditLog.objects.filter(
            timestamp__gte=dt_from,
            timestamp__lte=dt_to,
        )
        .select_related("user")
        .order_by("timestamp")
    )

    # ------------------------------------------------------------------ #
    # 3. Build PDF with reportlab                                          #
    # ------------------------------------------------------------------ #
    export_dir = _get_export_dir()
    filename = f"audit_export_{date_from}_{date_to}_{self.request.id}.pdf"
    file_path = os.path.join(export_dir, filename)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("TenderShield — Audit Log Export", styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(
        Paragraph(
            f"Date range: {date_from} to {date_to} | "
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | "
            f"Total entries: {len(entries)}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    # Advisory disclaimer (Requirement 11.6)
    story.append(
        Paragraph(
            "<b>Advisory disclaimer:</b> Fraud Risk Scores are advisory only. "
            "Human review is required before initiating any legal or administrative action.",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.8 * cm))

    # Table header
    col_widths = [3.5 * cm, 4.5 * cm, 3 * cm, 3 * cm, 4.5 * cm]
    table_data = [["Timestamp (UTC)", "Event Type", "User", "Entity", "Entity ID"]]

    for entry in entries:
        username = entry.user.username if entry.user else "system"
        table_data.append(
            [
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                entry.event_type,
                username,
                entry.affected_entity_type or "—",
                entry.affected_entity_id or "—",
            ]
        )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    doc.build(story)

    # Write buffer to file
    with open(file_path, "wb") as fh:
        fh.write(buffer.getvalue())

    # Relative path for URL construction
    relative_path = os.path.join(EXPORT_DIR_NAME, filename)

    # ------------------------------------------------------------------ #
    # 4. Write AuditLog entry for the export itself                        #
    # ------------------------------------------------------------------ #
    try:
        from authentication.models import User

        requesting_user = None
        if requested_by_user_id:
            requesting_user = User.objects.filter(pk=requested_by_user_id).first()

        AuditLog.objects.create(
            event_type=EventType.EXPORT_GENERATED,
            user=requesting_user,
            affected_entity_type="AuditLog",
            affected_entity_id="",
            data_snapshot={
                "date_from": date_from,
                "date_to": date_to,
                "entry_count": len(entries),
                "file": relative_path,
                "task_id": self.request.id,
            },
        )
    except Exception:
        logger.exception("Failed to write EXPORT_GENERATED AuditLog entry.")

    return {
        "status": "completed",
        "file_path": relative_path,
        "entry_count": len(entries),
    }
