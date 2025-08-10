"""
Django models for ISCC Hub.
"""

from django.db import models

from iscc_hub.fields import SequenceField


class IsccDeclaration(models.Model):
    # type: () -> None
    """
    Active ISCC declaration record.

    Represents the current state of an ISCC-ID declaration, materialized from
    the Event log. Each ISCC-ID has exactly one declaration record that gets
    fully replaced on updates.
    """

    # Primary identifier
    iscc_id = models.CharField(
        max_length=64, primary_key=True, help_text="ISCC-ID - the unique timestamp identifier"
    )

    # Event tracking
    event_seq = models.BigIntegerField(
        unique=True, db_index=True, help_text="Sequence number of the latest Event affecting this declaration"
    )

    # Core declaration data
    iscc_code = models.CharField(max_length=256, db_index=True, help_text="ISCC-CODE identifying the content")

    datahash = models.CharField(
        max_length=72, db_index=True, help_text="Blake3 multihash of the content (1e20 prefix + hash)"
    )

    nonce = models.CharField(
        max_length=32, unique=True, db_index=True, help_text="128-bit hex nonce preventing replay attacks"
    )

    # Actor identity
    actor = models.CharField(
        max_length=128, db_index=True, help_text="Ed25519 public key of the declaring actor"
    )

    # Optional fields
    gateway = models.URLField(
        max_length=2048, blank=True, default="", help_text="Gateway URL or URI template for metadata discovery"
    )

    metahash = models.CharField(
        max_length=72,
        blank=True,
        default="",
        db_index=True,
        help_text="Blake3 hash of seed metadata (optional commitment)",
    )

    # Timestamps
    declared_at = models.DateTimeField(
        db_index=True, help_text="Declaration timestamp from the signed IsccNote"
    )

    created_at = models.DateTimeField(db_index=True, help_text="When this ISCC-ID was first created")

    updated_at = models.DateTimeField(
        auto_now=True, db_index=True, help_text="When this declaration was last modified"
    )

    # Soft delete flag
    deleted = models.BooleanField(
        default=False, db_index=True, help_text="Soft delete flag - true if declaration has been deleted"
    )

    class Meta:
        db_table = "iscc_declaration"
        indexes = [
            # Discovery queries
            models.Index(fields=["iscc_code", "-created_at"]),
            models.Index(fields=["datahash", "-created_at"]),
            # Actor queries
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["actor", "iscc_code"]),
            models.Index(fields=["actor", "datahash"]),
            # Active declarations
            models.Index(fields=["deleted", "-created_at"]),
            # Event reconstruction
            models.Index(fields=["event_seq", "deleted"]),
        ]

    def __str__(self):
        # type: () -> str
        """String representation."""
        status = "deleted" if self.deleted else "active"
        return f"{self.iscc_id} ({status})"


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
