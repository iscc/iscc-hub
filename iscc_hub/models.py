"""
Django models for ISCC-HUB.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from iscc_hub.fields import HexField, IsccIDField, PubkeyField, SequenceField


class User(AbstractUser):
    """
    Custom user model for ISCC Hub.

    Extends Django's AbstractUser to allow future customization
    without complex migrations.
    """

    pass


class Hub(models.Model):
    """
    Active ISCC Hubs on the network.

    Stores configuration for all hubs in the ISCC network, including
    their identifiers, public keys, and endpoints. The authoritative list wille be synced from
    a smart contract.
    """

    # Primary identifier - matches ISCC_HUB_ID environment variable
    hub_id = models.PositiveSmallIntegerField(
        primary_key=True,
        help_text="Hub identifier (0-4095) - unique network identifier",
    )

    # Hub identity
    pubkey = PubkeyField(
        unique=True,
        db_index=True,
        help_text="Ed25519 public key of the hub for signature verification",
    )

    # Network endpoint
    url = models.URLField(
        max_length=2048,
        help_text="Base URL of the hub API endpoint (e.g. https://hub.example.com)",
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this hub is currently active on the network",
    )

    class Meta:
        db_table = "iscc_hub"
        verbose_name = "Hub"
        verbose_name_plural = "Hubs"

    def __str__(self):
        # type: () -> str
        """String representation of the Hub."""
        return f"Hub #{self.hub_id}: {self.url}"


class PubKey(models.Model):
    """
    Authorized public keys for permissioned mode.

    Can exist independently (unclaimed) or be linked to users.
    """

    # Core fields
    pubkey = models.CharField(max_length=48, primary_key=True, help_text="Ed25519 public key")

    # Authorization metadata
    label = models.CharField(max_length=255, blank=True, help_text="Human-readable label for this key")

    # Optional user linkage
    user = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pubkeys",
        help_text="User account managing this key (optional)",
    )

    # Status tracking
    is_active = models.BooleanField(default=True, db_index=True, help_text="Whether this key is currently authorized")

    class Meta:
        db_table = "iscc_pubkey"
        verbose_name = "Public Key"
        verbose_name_plural = "Public Keys"

    def __str__(self):
        if self.label:
            return f"{self.label} ({self.pubkey[:8]}...)"
        elif self.user:
            return f"{self.user.username}'s key ({self.pubkey[:8]}...)"
        return f"Unclaimed key ({self.pubkey[:8]}...)"


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

    # Event data stored as binary (canonicalized JSON)
    event_data = models.BinaryField(help_text="Event data stored as canonicalized JSON bytes")

    # Blake3 hash of the complete IsccEvent (seq, iscc_id, prev, note)
    event_hash = HexField(db_index=True, help_text="Blake3 hash of the canonicalized IsccEvent")

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

    datahash = HexField(max_length=34, db_index=True, help_text="Blake3 multihash of the content (1e20 prefix + hash)")

    nonce = HexField(
        max_length=16, unique=True, db_index=True, help_text="128-bit hex nonce preventing replay attacks"
    )

    # Actor identity
    pubkey = PubkeyField(db_index=True, help_text="Ed25519 public key of the declaring actor")

    controller = models.CharField(
        max_length=2048,
        blank=True,
        default="",
        help_text="DID or W3C CID Document URL identifying the key controller",
    )

    # Optional fields
    gateway = models.URLField(
        max_length=2048, blank=True, default="", help_text="Gateway URL or URI template for metadata discovery"
    )

    metahash = HexField(
        max_length=34,
        blank=True,
        null=True,
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

    def __str__(self):
        # type: () -> str
        """String representation."""
        status = "redacted" if self.redacted else "active"
        return f"{self.iscc_id} ({status})"


class LogState(models.Model):
    """
    Single-writer state for the portable, database-agnostic sequencer.

    Holds the explicit gapless counter and the monotonic microsecond clock that
    the sequencer reads and advances under a row lock inside one atomic
    transaction. Exactly one row exists per Hub; its primary key matches
    settings.ISCC_HUB_ID.
    """

    hub_id = models.PositiveSmallIntegerField(
        primary_key=True,
        help_text="Hub identifier (0-4095); matches settings.ISCC_HUB_ID",
    )

    tree_size = models.BigIntegerField(
        default=0,
        help_text="Number of committed records; the next 0-based leaf index equals this value",
    )

    last_timestamp_us = models.BigIntegerField(
        default=0,
        help_text="High-water mark of the Hub microsecond clock for monotonic ISCC-IDs",
    )

    class Meta:
        db_table = "iscc_logstate"
        verbose_name = "Log State"
        verbose_name_plural = "Log State"

    def __str__(self):
        # type: () -> str
        """String representation of the log state."""
        return f"LogState(hub={self.hub_id}, tree_size={self.tree_size})"


class LogRecord(models.Model):
    """
    Append-only transparency-log record (one row per Merkle-tree leaf).

    The `record` column holds the exact JCS-canonical bytes of the log-entry
    envelope ({$schema, iscc_id, note}) committed to the tree — the leaf preimage
    and the source of truth for verification. The remaining columns are auxiliary
    indexes derived from the record for fast write-path lookups and policy checks.
    """

    class RecordType(models.TextChoices):
        """Record discriminator derived from the signed note schema."""

        DECLARATION = "declaration", "Declaration"
        DELETION = "deletion", "Deletion"

    index = models.BigIntegerField(
        primary_key=True,
        help_text="Zero-based leaf index (sequence number); the first record is 0",
    )

    record = models.BinaryField(help_text="JCS-canonical log-entry envelope bytes (the leaf preimage)")

    iscc_id = IsccIDField(db_index=True, help_text="ISCC-ID carried by the record")

    type = models.CharField(
        max_length=11,
        choices=RecordType.choices,
        db_index=True,
        help_text="Record type derived from the note schema (declaration|deletion)",
    )

    nonce = HexField(unique=True, help_text="128-bit hex nonce; unique across all records")

    datahash = HexField(db_index=True, help_text="Blake3 multihash of the declared content")

    pubkey = PubkeyField(db_index=True, help_text="Ed25519 public key of the declaring actor")

    event_time = models.DateTimeField(db_index=True, help_text="Hub microsecond time when the record was sequenced")

    class Meta:
        db_table = "iscc_logrecord"
        verbose_name = "Log Record"
        verbose_name_plural = "Log Records"

    def __str__(self):
        # type: () -> str
        """String representation of the log record."""
        return f"LogRecord #{self.index}: {self.type} {self.iscc_id}"


class Checkpoint(models.Model):
    """
    Cryptographic checkpoint of the ISCC Hub event log.

    Creates verifiable snapshots of event history using Merkle trees
    and hash chaining for immutable audit trails.
    """

    # Auto-incrementing primary key
    id = models.AutoField(primary_key=True, help_text="Unique checkpoint identifier")

    # Event sequence range
    start = models.BigIntegerField(
        unique=True, db_index=True, help_text="Sequence number of the first event in this checkpoint"
    )

    end = models.BigIntegerField(db_index=True, help_text="Sequence number of the last event in this checkpoint")

    # Cryptographic hashes
    merkle_root = HexField(help_text="Blake3 hash of the Merkle tree root built from event hashes")

    prev = HexField(help_text="Hash of the previous checkpoint (Blake3 of empty bytes for genesis)")

    hash = HexField(unique=True, db_index=True, help_text="This checkpoint's hash: Blake3(merkle_root || prev)")

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="When this checkpoint was created")

    # External timestamping fields
    timestamp_type = models.CharField(
        max_length=10,
        choices=[
            ("RFC3161", "RFC 3161 TSA"),
            ("OTS", "OpenTimestamps"),
        ],
        null=True,
        blank=True,
        help_text="Type of external timestamp protocol used",
    )

    timestamp_token = models.TextField(
        null=True,
        blank=True,
        help_text="Base64-encoded timestamp token. Decode and verify using appropriate client library.",
    )

    class Meta:
        db_table = "iscc_checkpoint"
        verbose_name = "Checkpoint"
        verbose_name_plural = "Checkpoints"
        constraints = [
            # Django 6.0 renamed 'check' to 'condition' - ignore until django-types is updated
            models.CheckConstraint(condition=models.Q(end__gte=models.F("start")), name="checkpoint_end_gte_start"),  # pyright: ignore[reportCallIssue]
        ]

    def __str__(self):
        # type: () -> str
        """String representation of the Checkpoint."""
        return f"Checkpoint #{self.id}: events {self.start}-{self.end}"

    @property
    def event_count(self):
        # type: () -> int
        """Return the number of events in this checkpoint."""
        return self.end - self.start + 1
