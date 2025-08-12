#!/usr/bin/env python
"""
Reset development database for faster iteration.

This script:
- Deletes the existing dev database if it exists
- Creates and applies migrations
- Creates a demo/demo superuser account
- Loads test fixtures
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import django

# Configure Django settings
os.environ["DJANGO_SETTINGS_MODULE"] = "iscc_hub.settings"

# Set default environment variables if not set
os.environ.setdefault("ISCC_HUB_ID", "1")
os.environ.setdefault("ISCC_HUB_DOMAIN", "localhost:8000")
os.environ.setdefault("ISCC_HUB_SECKEY", "zHuboDevelopmentKeyDoNotUseInProduction")

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402


def reset_dev_database():
    # type: () -> None
    """Reset the development database."""
    # Get database path from settings
    db_name = settings.DATABASES["default"]["NAME"]
    db_path = Path(db_name)

    print(f"🔄 Resetting development database: {db_path}")

    # Close any existing connections
    connection.close()

    # Delete existing database if it exists
    if db_path.exists():
        print("  ✓ Deleting existing database...")
        try:
            db_path.unlink()
            print(f"    Database deleted: {db_path}")
        except PermissionError:
            print("    ⚠️  Could not delete database (may be in use). Continuing...")
    else:
        print("  ℹ️  No existing database found")

    # Check if migrations exist
    migrations_dir = Path("iscc_hub/migrations")
    has_migrations = migrations_dir.exists() and any(
        f.name.startswith("0001_") for f in migrations_dir.glob("*.py")
    )

    if not has_migrations:
        print("  ✓ Creating migrations...")
        call_command("makemigrations", verbosity=0)
        print("    Migrations created")
    else:
        print("  ℹ️  Using existing migrations")

    # Apply migrations
    print("  ✓ Applying migrations...")
    call_command("migrate", verbosity=0)
    print("    Migrations applied")

    # Create superuser
    print("  ✓ Creating demo superuser...")
    User = get_user_model()

    # Check if demo user already exists (shouldn't happen with fresh db, but just in case)
    if not User.objects.filter(username="demo").exists():
        User.objects.create_superuser(username="demo", email="demo@example.com", password="demo")
        print("    Created superuser: demo/demo")
    else:
        print("    Superuser 'demo' already exists")

    # Load test fixtures
    fixtures_file = Path("iscc_hub/fixtures/test_data.json")
    if fixtures_file.exists():
        print("  ✓ Loading test fixtures...")
        call_command("loaddata", "test_data", verbosity=0)
        print(f"    Loaded fixtures from {fixtures_file}")
    else:
        print(f"  ⚠️  No fixtures found at {fixtures_file}")
        print("     Run 'python scripts/generate_fixtures.py' to create fixtures")

    # Print summary
    print("\n✅ Database reset complete!")
    print("\n📊 Database summary:")

    # Import models here to avoid issues if migrations don't exist yet
    from iscc_hub.models import Event, IsccDeclaration

    event_count = Event.objects.count()
    declaration_count = IsccDeclaration.objects.count()
    active_count = IsccDeclaration.objects.filter(deleted=False).count()
    deleted_count = IsccDeclaration.objects.filter(deleted=True).count()

    print(f"  - Events: {event_count}")
    print(f"  - Declarations: {declaration_count}")
    print(f"    - Active: {active_count}")
    print(f"    - Deleted: {deleted_count}")

    print("\n🚀 You can now:")
    print("  - Run the dev server: uv run python manage.py runserver")
    print("  - Access admin at: http://localhost:8000/admin/")
    print("  - Login with: demo/demo")


if __name__ == "__main__":
    try:
        reset_dev_database()
    except KeyboardInterrupt:
        print("\n\n⚠️  Reset interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error resetting database: {e}")
        import traceback  # noqa: E402

        traceback.print_exc()
        sys.exit(1)
