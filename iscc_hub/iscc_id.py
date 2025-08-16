"""
Convenience class for ISCC-ID

Timestamp Precision:
    The ISCC-ID encodes a 52-bit microsecond timestamp representing the hub's
    declaration/logging time with microsecond precision. This is distinct from
    the client-side "timestamp" field in IsccNote, which uses millisecond
    precision for cross-platform compatibility.

    - Client timestamp (IsccNote.timestamp): Millisecond precision (3 decimal places)
      Time when the client created/signed the declaration
    - Hub timestamp (ISCC-ID): Microsecond precision (6 decimal places)
      Time when the hub sequenced/logged the declaration

The ISCC-IDv1 has the following format:
- Scheme Prefix: `ISCC:`
- Base32-Encoded concatenation of:
  - 16-bit ISCC-HEADER:
    - MAINTYPE = "0110" (ISCC-ID)
    - SUBTYPE  = "0000" (REALM 0 - Sandbox) or "0001" (REALM 1 - Operational)
    - VERSION  = "0001" (V1)
    - LENGTH   = "0001" (64-bit)
  - 64-bit ISCC-BODY:
    - 52-bit timestamp: Microseconds since 1970-01-01T00:00:00Z
    - 12-bit server-id: The Time Server ID (0-4095)
"""

from datetime import UTC, datetime, timezone
from functools import cached_property

import iscc_core as ic
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _get_header():
    # type: () -> bytes
    """Get ISCC-ID header bytes based on REALM configuration."""
    if settings.ISCC_HUB_REALM == 0:
        # Sandbox network (SUBTYPE="0000")
        return 0b0110000000010001.to_bytes(2, "big")
    elif settings.ISCC_HUB_REALM == 1:
        # Operational network (SUBTYPE="0001")
        return 0b0110000100010001.to_bytes(2, "big")
    else:
        raise ImproperlyConfigured(f"Invalid ISCC_HUB_REALM: {settings.ISCC_HUB_REALM}")


class IsccID:
    """Convenience class to manage various ISCC-IDv1 representations."""

    HEADER = _get_header()

    def __init__(self, value):
        # type: (str|bytes|IsccID) -> None
        """Initialize ISCC-IDv1 from canonical string representation or raw bytes."""

        # Canonical String Representation
        if isinstance(value, str):
            mt, st, vs, ln, body = ic.iscc_decode(value)
        # ISCC-BODY with or without ISCC-HEADER
        elif isinstance(value, bytes):
            if len(value) not in (8, 10):
                raise ValueError(f"Can´t inititilize `IsccID` from bytes with length {len(value)}")
            body = value if len(value) == 8 else value[2:]
        elif isinstance(value, IsccID):
            body = value.bytes_body
        else:
            raise ValueError(f"Can´t inititilize `IsccID` from type {type(value)}")

        # 8-byte internal representation of ISCC-ID without ISCC-HEADER
        self._bytes_body: bytes = body
        self._cached_str = None

    def __str__(self):
        # type: () -> str
        """Canonical ISCC-IDv1 string representation."""
        if self._cached_str is None:
            self._cached_str = f"ISCC:{ic.encode_base32(self.HEADER + self._bytes_body)}"
        return self._cached_str

    def __repr__(self):
        # type: () -> str
        """Return a string representation for debugging."""
        return f"IsccID('{self}')"

    def __bytes__(self):
        """Efficient 8-bytes representation of ISCC-IDv1 without ISCC-HEADER."""
        return self._bytes_body

    @property
    def bytes_body(self):
        # type: () -> bytes
        """Full ISCC-BODY as raw bytes."""
        return self._bytes_body

    @cached_property
    def uint_body(self):
        # type: () -> int
        """ISCC-BODY as unsigned integer (52-bit µs timestamp + 12-bit server_id)."""
        return int.from_bytes(self._bytes_body, "big", signed=False)

    @cached_property
    def timestamp_micros(self):
        # type: () -> int
        """Timestamp in microseconds since epoch."""
        return self.uint_body >> 12

    @cached_property
    def timestamp_iso(self):
        # type: () -> str
        """Timestamp as ISO 8601 string with microsecond precision."""
        dt = datetime.fromtimestamp(self.timestamp_micros / 1_000_000, tz=UTC)
        # isoformat() gives “…+00:00”; swap that for the RFC-friendly “Z”
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @classmethod
    def from_timestamp(cls, ts_us, hub_id):
        # type: (int, int) -> IsccID
        """Instantiate ISCC-IDv1 from microsecond timestamp and hub_id."""
        if not (0 <= hub_id <= 4095):
            raise ValueError(f"Hub-ID must be between 0 and 4095, got {hub_id}")

        if ts_us < 0:
            raise ValueError(f"Timestamp must be non-negative, got {ts_us}")

        # Check if timestamp fits in 52 bits
        max_timestamp = (1 << 52) - 1
        if ts_us > max_timestamp:
            raise ValueError(f"Timestamp too large, maximum is {max_timestamp}, got {ts_us}")

        # Combine 52-bit timestamp (shifted left 12 bits) with 12-bit hub_id
        uint_body = (ts_us << 12) | hub_id

        # Convert to 8-byte representation
        bytes_body = uint_body.to_bytes(8, "big")

        return cls(bytes_body)

    @cached_property
    def hub_id(self):
        # type: () -> int
        """Hub-ID (12-bit LSB - 0-4095)."""
        return self.uint_body & 0xFFF

    def __eq__(self, other):
        # type: (object) -> bool
        """Check equality based on the internal bytes representation."""
        if isinstance(other, IsccID):
            return self._bytes_body == other._bytes_body
        elif isinstance(other, str):
            try:
                other_id = IsccID(other)
                return self._bytes_body == other_id._bytes_body
            except (ValueError, Exception):
                return False
        elif isinstance(other, bytes):
            # Compare with raw bytes (8 or 10 bytes)
            if len(other) == 8:
                return self._bytes_body == other
            elif len(other) == 10:
                return self._bytes_body == other[2:]
            else:
                return False
        return NotImplemented

    def __hash__(self):
        # type: () -> int
        """Return hash based on the internal bytes representation."""
        return hash(self._bytes_body)

    def __lt__(self, other):
        # type: (object) -> bool
        """Compare based on timestamp, then server_id for chronological ordering."""
        if not isinstance(other, IsccID):
            if isinstance(other, str | bytes):
                try:
                    other = IsccID(other)
                except (ValueError, Exception):
                    return NotImplemented
            else:
                return NotImplemented

        # Compare timestamps first
        if self.timestamp_micros != other.timestamp_micros:
            return self.timestamp_micros < other.timestamp_micros
        # If timestamps are equal, compare hub_ids
        return self.hub_id < other.hub_id

    def __le__(self, other):
        # type: (object) -> bool
        """Less than or equal comparison."""
        return self == other or self < other

    def __gt__(self, other):
        # type: (object) -> bool
        """Greater than comparison."""
        if not isinstance(other, IsccID):
            if isinstance(other, str | bytes):
                try:
                    other = IsccID(other)
                except (ValueError, Exception):
                    return NotImplemented
            else:
                return NotImplemented
        return not self <= other

    def __ge__(self, other):
        # type: (object) -> bool
        """Greater than or equal comparison."""
        return self == other or self > other


if __name__ == "__main__":  # pragma: no cover
    iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
    print("Canonical: ", iid)
    print("Body Bytes:", iid.bytes_body)
    print("Body UINT: ", iid.uint_body)
    print("Time µs:   ", iid.timestamp_micros)
    print("Time ISO:  ", iid.timestamp_iso)
    print("Hub-ID:    ", iid.hub_id)
    print("Roundtrip: ", IsccID(iid.bytes_body))
    print("Roundtrip: ", IsccID.from_timestamp(1746171541264773, 0))

    print("repr():    ", repr(iid))
    print("Hashable:  ", hash(iid))

    # Equality
    iid2 = IsccID("ISCC:MAIWGQRD43YZQUAA")
    print("Equal:     ", iid == iid2)
    print("Equal str: ", iid == "ISCC:MAIWGQRD43YZQUAA")

    # Ordering
    iid3 = IsccID.from_timestamp(1746171541264773 + 1000000, 0)
    print("Ordering:  ", iid < iid3, "(older < newer)")

    # Use in collections
    id_set = {iid, iid2, iid3}
    print("Set size:  ", len(id_set), "(deduped)")
    print("Sorted:    ", [str(x) for x in sorted(id_set)])
