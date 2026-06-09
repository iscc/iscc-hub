"""
Tests for Django models.
"""

import pytest

from iscc_hub.models import IsccDeclaration, PubKey, User
from tests.conftest import generate_test_iscc_id


@pytest.mark.django_db
def test_hub_str_method():
    # type: () -> None
    """
    Test Hub __str__ method.
    """
    from iscc_hub.models import Hub

    hub = Hub(hub_id=42, pubkey="z6MkfrVYbLejh9Hv7Qmx4B2P681wBfPFkcHFaLwWDmSj8Kzv", url="https://hub.example.com")
    assert str(hub) == "Hub #42: https://hub.example.com"


@pytest.mark.django_db
def test_pubkey_str_with_label():
    # type: () -> None
    """
    Test PubKey __str__ method with label.
    """
    pubkey = PubKey(pubkey="abcdefghijklmnopqrstuvwxyz123456789", label="My Test Key")
    assert str(pubkey) == "My Test Key (abcdefgh...)"


@pytest.mark.django_db
def test_pubkey_str_with_user_no_label():
    # type: () -> None
    """
    Test PubKey __str__ method with user but no label.
    """
    user = User(username="testuser")
    pubkey = PubKey(pubkey="abcdefghijklmnopqrstuvwxyz123456789", user=user)
    assert str(pubkey) == "testuser's key (abcdefgh...)"


@pytest.mark.django_db
def test_pubkey_str_no_label_no_user():
    # type: () -> None
    """
    Test PubKey __str__ method without label or user.
    """
    pubkey = PubKey(pubkey="abcdefghijklmnopqrstuvwxyz123456789")
    assert str(pubkey) == "Unclaimed key (abcdefgh...)"


# IsccDeclaration Model Tests


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_creation():
    # type: () -> None
    """
    Test basic IsccDeclaration model creation.
    """
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    assert declaration.iscc_id == "ISCC:MEAJU3PC4ICWCTYI"
    assert declaration.redacted is False
    assert declaration.gateway == ""
    assert declaration.metahash is None  # HexField returns None for empty values
    assert declaration.updated_at is not None


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_with_optional_fields():
    # type: () -> None
    """
    Test IsccDeclaration with optional fields.
    """
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://gateway.example.com",
        metahash="1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678",
    )

    assert declaration.gateway == "https://gateway.example.com"
    assert declaration.metahash == "1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678"


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_str_representation():
    # type: () -> None
    """
    Test IsccDeclaration string representation.
    """
    # Test active declaration
    active_declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=60),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )
    assert str(active_declaration) == f"{generate_test_iscc_id(seq=60)} (active)"

    # Test redacted declaration
    redacted_declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=61),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="001abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        redacted=True,
    )
    assert str(redacted_declaration) == f"{generate_test_iscc_id(seq=61)} (redacted)"


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_unique_constraints():
    # type: () -> None
    """
    Test unique constraints on IsccDeclaration.
    """
    from django.db import IntegrityError

    # Create first declaration
    IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=70),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    # Test iscc_id uniqueness (primary key)
    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=70),  # Duplicate
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="001abcd1234567890abcdef123456789",
            pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        )


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_unique_nonce():
    # type: () -> None
    """
    Test that the nonce field must be unique across declarations.
    """
    from django.db import IntegrityError

    IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=75),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=76),
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="000abcd1234567890abcdef123456789",  # Duplicate
            pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        )


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_redacted_field():
    # type: () -> None
    """
    Test redacted field functionality.
    """
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=81),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://malicious.example.com",
    )

    # Initially not redacted (default value)
    assert declaration.redacted is False

    # Redact the declaration
    declaration.redacted = True
    declaration.save()

    # Verify redaction
    declaration = IsccDeclaration.objects.get(iscc_id=generate_test_iscc_id(seq=81))
    assert declaration.redacted is True

    # Verify filtering non-redacted declarations
    non_redacted = IsccDeclaration.objects.filter(redacted=False)
    assert generate_test_iscc_id(seq=81) not in [d.iscc_id for d in non_redacted]

    # Verify filtering redacted declarations
    redacted = IsccDeclaration.objects.filter(redacted=True)
    assert generate_test_iscc_id(seq=81) in [d.iscc_id for d in redacted]


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_indexes():
    # type: () -> None
    """
    Test that indexes work for efficient queries.
    """
    # Generate test Ed25519 public keys for testing
    test_actors = [
        "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",  # actor 0
        "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",  # actor 1
        "z6MkfrVYbLejh9Hv7Qmx4B2P681wBfPFkcHFaLwWDmSj8Kzv",  # actor 2
    ]

    # Create multiple declarations
    for i in range(5):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=90 + i),
            iscc_code=f"ISCC:CODE{i % 2}",  # Two different codes
            datahash=f"1e20{'a' * 64}" if i % 2 == 0 else f"1e20{'b' * 64}",
            nonce=f"{i:03d}abcd1234567890abcdef123456789",
            pubkey=test_actors[i % 3],  # Three different pubkeys
        )

    # Test indexed queries
    # Query by iscc_code
    results = IsccDeclaration.objects.filter(iscc_code="ISCC:CODE0")
    assert results.count() == 3

    # Query by datahash
    results = IsccDeclaration.objects.filter(datahash=f"1e20{'a' * 64}")
    assert results.count() == 3

    # Query by pubkey
    results = IsccDeclaration.objects.filter(pubkey=test_actors[0])
    assert results.count() == 2

    # Query by pubkey and iscc_code
    results = IsccDeclaration.objects.filter(pubkey=test_actors[0], iscc_code="ISCC:CODE0")
    assert results.count() == 1


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_update():
    # type: () -> None
    """
    Test updating an IsccDeclaration (full replacement).
    """
    # Create initial declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=100),
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        pubkey="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://old.gateway.com",
    )

    original_updated_at = declaration.updated_at

    # Add small delay to ensure timestamp changes (Windows timing precision issue)
    import time

    time.sleep(0.001)

    # Simulate full replacement update
    declaration.iscc_code = "ISCC:NEWCODE"
    declaration.datahash = "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    declaration.pubkey = "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB"  # Different valid Ed25519 key
    declaration.gateway = "https://new.gateway.com"
    declaration.save()

    # Verify updates
    declaration = IsccDeclaration.objects.get(iscc_id=generate_test_iscc_id(seq=100))
    assert declaration.iscc_code == "ISCC:NEWCODE"
    assert declaration.datahash == "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    assert declaration.pubkey == "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB"
    assert declaration.gateway == "https://new.gateway.com"
    assert declaration.updated_at > original_updated_at  # auto_now should update


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_model_meta():
    # type: () -> None
    """
    Test IsccDeclaration model Meta configuration.
    """
    # Test db_table
    assert IsccDeclaration._meta.db_table == "iscc_declaration"

    # Test verbose names
    assert IsccDeclaration._meta.verbose_name == "Declaration"
    assert IsccDeclaration._meta.verbose_name_plural == "Declarations"

    # Test primary key
    pk_field = IsccDeclaration._meta.pk
    assert pk_field.name == "iscc_id"

    # Test that indexes have been removed (for now)
    assert len(IsccDeclaration._meta.indexes) == 0


@pytest.mark.django_db(transaction=True)
def test_iscc_declaration_duplicate_content_allowed():
    # type: () -> None
    """
    Test that the same actor can declare the same content multiple times.
    This verifies no database constraints prevent duplicate declarations.
    """
    pubkey = "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1"
    iscc_code = "ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ"
    datahash = "1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c"

    # Create first declaration
    declaration1 = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=110),
        iscc_code=iscc_code,
        datahash=datahash,
        nonce="000abcd1234567890abcdef123456789",
        pubkey=pubkey,
    )

    # Create second declaration with same pubkey, iscc_code, and datahash
    # This should succeed as we removed unique constraints
    declaration2 = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=111),
        iscc_code=iscc_code,  # Same code
        datahash=datahash,  # Same hash
        nonce="001abcd1234567890abcdef123456789",  # Different nonce
        pubkey=pubkey,  # Same pubkey
    )

    # Verify both exist
    assert declaration1.iscc_id == generate_test_iscc_id(seq=110)
    assert declaration2.iscc_id == generate_test_iscc_id(seq=111)

    # Query declarations by pubkey and iscc_code
    declarations = IsccDeclaration.objects.filter(pubkey=pubkey, iscc_code=iscc_code)
    assert declarations.count() == 2
