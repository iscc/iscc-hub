"""
Django models for ISCC Hub.
"""

from django.db import models

from iscc_hub.fields import SequenceField


class Event(models.Model):
    # type: () -> None
    """
    Append-only event log for ISCC declarations.

    Stores IsccNote declarations with gapless sequence numbers,
    supporting both initial declarations and updates.
    """

    class EventType(models.IntegerChoices):
        # type: () -> None
        """
        Event types for ISCC declarations.
        """

        CREATED = 1, "Created"
        UPDATED = 2, "Updated"
        DELETED = 3, "Deleted"

    # Gapless sequence number as primary key
    seq = SequenceField(primary_key=True, help_text="Gapless sequence number for events")

    # Event type
    event_type = models.PositiveSmallIntegerField(
        choices=EventType.choices,
        default=EventType.CREATED,
        db_index=True,
        help_text="Type of event (1=CREATED, 2=UPDATED, 3=DELETED)",
    )

    # ISCC-ID assigned to the declaration (can be non-unique for updates)
    iscc_id = models.CharField(max_length=64, db_index=True, help_text="ISCC-ID assigned to the declaration")

    # The IsccNote stored as JSON
    iscc_note = models.JSONField(help_text="The logged IsccNote as JSON")

    # Auto-generated timestamp when the event is created
    timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True, help_text="Timestamp when the event was logged"
    )

    class Meta:
        db_table = "iscc_event"
        ordering = ["seq"]
        indexes = [
            models.Index(fields=["iscc_id", "seq"]),
            models.Index(fields=["timestamp"]),
        ]
        verbose_name = "ISCC Event"
        verbose_name_plural = "ISCC Events"

    def __str__(self):
        # type: () -> str
        """
        String representation of the Event.
        """
        return f"Event #{self.seq}: {self.get_event_type_display()} {self.iscc_id}"  # type: ignore[attr-defined]
