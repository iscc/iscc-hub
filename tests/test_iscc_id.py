"""Tests for the IsccID class."""

import pytest

from iscc_hub.iscc_id import IsccID


class TestIsccIDInitialization:
    """Test various ways to initialize an IsccID."""

    def test_init_from_string(self):
        # type: () -> None
        """Test initializing from canonical string representation."""
        iscc_str = "ISCC:MAIWGQRD43YZQUAA"
        iid = IsccID(iscc_str)
        assert str(iid) == iscc_str
        assert len(bytes(iid)) == 8

    def test_init_from_bytes_body_only(self):
        # type: () -> None
        """Test initializing from 8-byte body."""
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(body)
        assert bytes(iid) == body
        assert len(bytes(iid)) == 8

    def test_init_from_bytes_with_header(self):
        # type: () -> None
        """Test initializing from 10-byte data (header + body)."""
        header = IsccID.HEADER
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        full_bytes = header + body
        iid = IsccID(full_bytes)
        assert bytes(iid) == body
        assert len(bytes(iid)) == 8

    def test_init_from_another_iscc_id(self):
        # type: () -> None
        """Test initializing from another IsccID instance."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID(iid1)
        assert iid1 == iid2
        assert bytes(iid1) == bytes(iid2)

    def test_init_invalid_type(self):
        # type: () -> None
        """Test initialization with invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Can´t inititilize `IsccID` from type"):
            IsccID(12345)

    def test_init_invalid_bytes_length(self):
        # type: () -> None
        """Test initialization with invalid bytes length raises ValueError."""
        with pytest.raises(ValueError, match="Can´t inititilize `IsccID` from bytes with length"):
            IsccID(b"short")


class TestIsccIDProperties:
    """Test IsccID property accessors."""

    def test_bytes_body(self):
        # type: () -> None
        """Test bytes_body property returns correct bytes."""
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(body)
        assert iid.bytes_body == body

    def test_uint_body(self):
        # type: () -> None
        """Test uint_body property returns correct unsigned integer."""
        body = b"\x00\x00\x00\x00\x00\x00\x00\x01"
        iid = IsccID(body)
        assert iid.uint_body == 1

    def test_timestamp_micros(self):
        # type: () -> None
        """Test timestamp extraction from ISCC-ID."""
        # Create ISCC-ID with known timestamp
        ts_us = 1000000000000  # 1 million seconds in microseconds
        hub_id = 0
        iid = IsccID.from_timestamp(ts_us, hub_id)
        assert iid.timestamp_micros == ts_us

    def test_hub_id(self):
        # type: () -> None
        """Test server ID extraction from ISCC-ID."""
        # Create ISCC-ID with known server ID
        ts_us = 1000000000000
        hub_id = 4095  # Maximum server ID
        iid = IsccID.from_timestamp(ts_us, hub_id)
        assert iid.hub_id == hub_id

    def test_timestamp_iso(self):
        # type: () -> None
        """Test ISO timestamp formatting."""
        # Create ISCC-ID with known timestamp
        ts_us = 1577836800000000  # 2020-01-01 00:00:00 UTC in microseconds
        iid = IsccID.from_timestamp(ts_us, 0)
        iso_str = iid.timestamp_iso
        assert iso_str == "2020-01-01T00:00:00.000000Z"
        assert iso_str.endswith("Z")


class TestIsccIDFromTimestamp:
    """Test creating IsccID from timestamp and server ID."""

    def test_from_timestamp_basic(self):
        # type: () -> None
        """Test basic creation from timestamp."""
        ts_us = 1234567890123456
        hub_id = 123
        iid = IsccID.from_timestamp(ts_us, hub_id)
        assert iid.timestamp_micros == ts_us
        assert iid.hub_id == hub_id

    def test_from_timestamp_min_values(self):
        # type: () -> None
        """Test creation with minimum valid values."""
        iid = IsccID.from_timestamp(0, 0)
        assert iid.timestamp_micros == 0
        assert iid.hub_id == 0

    def test_from_timestamp_max_hub_id(self):
        # type: () -> None
        """Test creation with maximum server ID."""
        iid = IsccID.from_timestamp(1000000, 4095)
        assert iid.hub_id == 4095

    def test_from_timestamp_hub_id_too_large(self):
        # type: () -> None
        """Test creation with server ID > 4095 raises ValueError."""
        with pytest.raises(ValueError, match="Hub-ID must be between 0 and 4095"):
            IsccID.from_timestamp(1000000, 4096)

    def test_from_timestamp_negative_hub_id(self):
        # type: () -> None
        """Test creation with negative server ID raises ValueError."""
        with pytest.raises(ValueError, match="Hub-ID must be between 0 and 4095"):
            IsccID.from_timestamp(1000000, -1)

    def test_from_timestamp_negative_timestamp(self):
        # type: () -> None
        """Test creation with negative timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Timestamp must be non-negative"):
            IsccID.from_timestamp(-1, 0)

    def test_from_timestamp_too_large(self):
        # type: () -> None
        """Test creation with timestamp > 52 bits raises ValueError."""
        max_timestamp = (1 << 52) - 1
        with pytest.raises(ValueError, match="Timestamp too large"):
            IsccID.from_timestamp(max_timestamp + 1, 0)


class TestIsccIDEquality:
    """Test equality comparison."""

    def test_eq_same_instance(self):
        # type: () -> None
        """Test equality with same instance."""
        iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid == iid

    def test_eq_same_value(self):
        # type: () -> None
        """Test equality with same value."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid1 == iid2

    def test_eq_different_value(self):
        # type: () -> None
        """Test inequality with different value."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIZGUNTY2V446HQ")
        assert iid1 != iid2

    def test_eq_with_string(self):
        # type: () -> None
        """Test equality comparison with string."""
        iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid == "ISCC:MAIWGQRD43YZQUAA"
        assert iid != "ISCC:MAIZGUNTY2V446HQ"

    def test_eq_with_invalid_string(self):
        # type: () -> None
        """Test equality with invalid string returns False."""
        iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid != "invalid"
        assert iid != "NOTISCC:MAIWGQRD43YZQUAA"

    def test_eq_with_bytes_8(self):
        # type: () -> None
        """Test equality comparison with 8-byte body."""
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(body)
        assert iid == body
        assert iid != b"\x00\x00\x00\x00\x00\x00\x00\x00"

    def test_eq_with_bytes_10(self):
        # type: () -> None
        """Test equality comparison with 10-byte (header + body)."""
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(body)
        full_bytes = IsccID.HEADER + body
        assert iid == full_bytes

    def test_eq_with_wrong_length_bytes(self):
        # type: () -> None
        """Test equality with wrong length bytes returns False."""
        iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid != b"short"
        assert iid != b"way too long bytes here"

    def test_eq_with_other_types(self):
        # type: () -> None
        """Test equality with other types returns NotImplemented."""
        iid = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert iid.__eq__(12345) == NotImplemented
        assert iid.__eq__([1, 2, 3]) == NotImplemented


class TestIsccIDHashing:
    """Test hashing behavior."""

    def test_hash_consistent(self):
        # type: () -> None
        """Test hash is consistent for same value."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert hash(iid1) == hash(iid2)

    def test_hash_different_for_different_values(self):
        # type: () -> None
        """Test hash is different for different values."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIZGUNTY2V446HQ")
        assert hash(iid1) != hash(iid2)

    def test_use_in_set(self):
        # type: () -> None
        """Test IsccID can be used in sets."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIWGQRD43YZQUAA")  # Same value
        iid3 = IsccID("ISCC:MAIZGUNTY2V446HQ")

        id_set = {iid1, iid2, iid3}
        assert len(id_set) == 2  # iid1 and iid2 are the same

    def test_use_as_dict_key(self):
        # type: () -> None
        """Test IsccID can be used as dictionary key."""
        iid1 = IsccID("ISCC:MAIWGQRD43YZQUAA")
        iid2 = IsccID("ISCC:MAIZGUNTY2V446HQ")

        d = {iid1: "value1", iid2: "value2"}
        assert d[iid1] == "value1"
        assert d[iid2] == "value2"

        # Same ID should access same value
        iid1_copy = IsccID("ISCC:MAIWGQRD43YZQUAA")
        assert d[iid1_copy] == "value1"


class TestIsccIDRepr:
    """Test string representations."""

    def test_str(self):
        # type: () -> None
        """Test __str__ returns canonical representation."""
        iscc_str = "ISCC:MAIWGQRD43YZQUAA"
        iid = IsccID(iscc_str)
        assert str(iid) == iscc_str

    def test_repr(self):
        # type: () -> None
        """Test __repr__ returns debug representation."""
        iscc_str = "ISCC:MAIWGQRD43YZQUAA"
        iid = IsccID(iscc_str)
        assert repr(iid) == f"IsccID('{iscc_str}')"

    def test_str_cached(self):
        # type: () -> None
        """Test string representation is cached."""
        body = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(body)
        str1 = str(iid)
        str2 = str(iid)
        # Should be the exact same object due to caching
        assert str1 is str2


class TestIsccIDOrdering:
    """Test ordering comparisons."""

    def test_lt_by_timestamp(self):
        # type: () -> None
        """Test less than comparison by timestamp."""
        iid1 = IsccID.from_timestamp(1000000, 0)
        iid2 = IsccID.from_timestamp(2000000, 0)
        assert iid1 < iid2
        assert not iid2 < iid1

    def test_lt_by_hub_id_when_timestamp_equal(self):
        # type: () -> None
        """Test less than comparison by server ID when timestamps are equal."""
        iid1 = IsccID.from_timestamp(1000000, 10)
        iid2 = IsccID.from_timestamp(1000000, 20)
        assert iid1 < iid2
        assert not iid2 < iid1

    def test_lt_with_string(self):
        # type: () -> None
        """Test less than comparison with string."""
        iid1 = IsccID.from_timestamp(1000000, 0)
        iid2_str = str(IsccID.from_timestamp(2000000, 0))
        assert iid1 < iid2_str

    def test_lt_with_bytes(self):
        # type: () -> None
        """Test less than comparison with bytes."""
        iid1 = IsccID.from_timestamp(1000000, 0)
        iid2 = IsccID.from_timestamp(2000000, 0)
        assert iid1 < bytes(iid2)

    def test_lt_with_invalid_type(self):
        # type: () -> None
        """Test less than with invalid type returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__lt__(12345) == NotImplemented

    def test_lt_with_invalid_string(self):
        # type: () -> None
        """Test less than with invalid string returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__lt__("invalid_string") == NotImplemented

    def test_lt_with_invalid_bytes(self):
        # type: () -> None
        """Test less than with invalid bytes returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__lt__(b"invalid") == NotImplemented

    def test_le(self):
        # type: () -> None
        """Test less than or equal comparison."""
        iid1 = IsccID.from_timestamp(1000000, 0)
        iid2 = IsccID.from_timestamp(2000000, 0)
        iid3 = IsccID.from_timestamp(1000000, 0)
        assert iid1 <= iid2
        assert iid1 <= iid3
        assert not iid2 <= iid1

    def test_gt(self):
        # type: () -> None
        """Test greater than comparison."""
        iid1 = IsccID.from_timestamp(2000000, 0)
        iid2 = IsccID.from_timestamp(1000000, 0)
        assert iid1 > iid2
        assert not iid2 > iid1

    def test_gt_with_invalid_type(self):
        # type: () -> None
        """Test greater than with invalid type returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__gt__(12345) == NotImplemented

    def test_gt_with_invalid_string(self):
        # type: () -> None
        """Test greater than with invalid string returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__gt__("invalid_string") == NotImplemented

    def test_gt_with_invalid_bytes(self):
        # type: () -> None
        """Test greater than with invalid bytes returns NotImplemented."""
        iid = IsccID.from_timestamp(1000000, 0)
        assert iid.__gt__(b"invalid") == NotImplemented

    def test_ge(self):
        # type: () -> None
        """Test greater than or equal comparison."""
        iid1 = IsccID.from_timestamp(2000000, 0)
        iid2 = IsccID.from_timestamp(1000000, 0)
        iid3 = IsccID.from_timestamp(2000000, 0)
        assert iid1 >= iid2
        assert iid1 >= iid3
        assert not iid2 >= iid1

    def test_sorting(self):
        # type: () -> None
        """Test IsccIDs can be sorted chronologically."""
        iid1 = IsccID.from_timestamp(3000000, 0)
        iid2 = IsccID.from_timestamp(1000000, 0)
        iid3 = IsccID.from_timestamp(2000000, 0)
        iid4 = IsccID.from_timestamp(2000000, 10)  # Same timestamp, different server

        sorted_list = sorted([iid1, iid2, iid3, iid4])
        assert sorted_list == [iid2, iid3, iid4, iid1]

        # Verify the specific ordering with same timestamp
        assert sorted_list[1].hub_id < sorted_list[2].hub_id


class TestIsccIDRoundtrip:
    """Test roundtrip conversions."""

    def test_roundtrip_string(self):
        # type: () -> None
        """Test roundtrip from string."""
        original = "ISCC:MAIWGQRD43YZQUAA"
        iid = IsccID(original)
        assert str(iid) == original

    def test_roundtrip_bytes(self):
        # type: () -> None
        """Test roundtrip from bytes."""
        original = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
        iid = IsccID(original)
        assert bytes(iid) == original

    def test_roundtrip_from_timestamp(self):
        # type: () -> None
        """Test roundtrip from timestamp creation."""
        ts_us = 1234567890123456
        hub_id = 123
        iid = IsccID.from_timestamp(ts_us, hub_id)

        # Extract and verify
        assert iid.timestamp_micros == ts_us
        assert iid.hub_id == hub_id

        # Create new from bytes and verify
        iid2 = IsccID(bytes(iid))
        assert iid2.timestamp_micros == ts_us
        assert iid2.hub_id == hub_id
