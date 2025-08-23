"""
Django models for ISCC Hub.
"""

from django.db import models

from iscc_hub.fields import HexField, IsccIDField, PubkeyField, SequenceField


class Event(models.Model):
    """
    Append-only event log for ISCC declarations.

    Stores IsccNote declarations with gapless sequence numbers,
    supporting both initial declarations and updates.
    """

    class EventType(models.IntegerChoices):
        """
        Event types for ISCC declarations.
        """

        CREATED = 1, "Created"
        UPDATED = 2, "Updated"
        DELETED = 3, "Deleted"

    # Gapless sequence number as primary key
    seq = SequenceField(primary_key=True, help_text="Gapless sequence number for events")

    # ISCC-ID assigned to the declaration (can be non-unique for updates)
    iscc_id = IsccIDField(db_index=True, help_text="ISCC-ID assigned to the declaration")

    # Unique Nonce
    nonce = HexField(unique=True, help_text="128-bit hex nonce preventing replay attacks")

    # For application side detection of duplicate declarations (if desired)
    datahash = HexField(db_index=True, help_text="Hash of the declared content")

    # Public key of the declaring actor
    pubkey = PubkeyField(db_index=True, help_text="Ed25519 public key of the declaring actor")

    # Event type
    event_type = models.PositiveSmallIntegerField(
        choices=EventType.choices,
        default=EventType.CREATED,
        db_index=True,
        help_text="Type of event (1=CREATED, 2=UPDATED, 3=DELETED)",
    )

    # The IsccNote stored as JSON
    iscc_note = models.JSONField(help_text="The logged IsccNote as JSON")

    # Event timestamp - when this specific event occurred
    # For CREATED events: same as ISCC-ID timestamp (initial declaration time)
    # For UPDATED/DELETED events: when the update/deletion happened
    event_time = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this event was logged (for updates/deletes, differs from ISCC-ID timestamp)",
    )

    class Meta:
        db_table = "iscc_event"
        indexes = [
            models.Index(fields=["iscc_id", "seq"]),
            models.Index(fields=["event_time"]),
        ]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self):
        # type: () -> str
        """
        String representation of the Event.
        """
        return f"Event #{self.seq}: {self.get_event_type_display()} {self.iscc_id}"  # type: ignore[attr-defined]


class IsccDeclaration(models.Model):
    """
    Active ISCC declaration record.

    Represents the current state of an ISCC-ID declaration, materialized from
    the Event log. Each ISCC-ID has exactly one declaration record that gets
    fully replaced on updates.
    """

    # Primary identifier
    iscc_id = IsccIDField(primary_key=True, help_text="ISCC-ID - the unique timestamp identifier")

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
    actor = models.CharField(max_length=128, db_index=True, help_text="Ed25519 public key of the declaring actor")

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
    updated_at = models.DateTimeField(
        auto_now=True, db_index=True, help_text="When this declaration was last modified"
    )

    # Redaction flag for malicious content
    redacted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Admin redaction flag - disables resolution of malicious declarations on this HUB",
    )

    class Meta:
        db_table = "iscc_declaration"
        verbose_name = "Declaration"
        verbose_name_plural = "Declarations"
        indexes = [
            # Discovery queries (use iscc_id for chronological ordering)
            models.Index(fields=["iscc_code", "-iscc_id"]),
            models.Index(fields=["datahash", "-iscc_id"]),
            # Actor queries
            models.Index(fields=["actor", "-iscc_id"]),
            models.Index(fields=["actor", "iscc_code"]),
            models.Index(fields=["actor", "datahash"]),
            # Admin redaction
            models.Index(fields=["redacted", "-iscc_id"]),
        ]

    def __str__(self):
        # type: () -> str
        """String representation."""
        status = "redacted" if self.redacted else "active"
        return f"{self.iscc_id} ({status})"
