#!/usr/bin/env python
"""
Database management commands for development.

This script provides:
- init: Initialize database if it doesn't exist (skips if already exists)
- reset: Force reset database (deletes existing and recreates)
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


def delete_database(db_path):
    # type: (Path) -> bool
    """
    Delete the database file if it exists.

    :param db_path: Path to the database file
    :return: True if database was deleted, False otherwise
    """
    if db_path.exists():
        print("  ✓ Deleting existing database...")
        try:
            # Close any existing connections
            connection.close()
            db_path.unlink()
            print(f"    Database deleted: {db_path}")
            return True
        except PermissionError:
            print("    ⚠️  Could not delete database (may be in use). Continuing...")
            return False
    return False


def ensure_migrations():
    # type: () -> bool
    """
    Ensure migrations exist, creating them if necessary.

    :return: True if migrations were created, False if they already existed
    """
    migrations_dir = Path("iscc_hub/migrations")
    has_migrations = migrations_dir.exists() and any(f.name.startswith("0001_") for f in migrations_dir.glob("*.py"))

    if not has_migrations:
        print("  ✓ Creating migrations...")
        call_command("makemigrations", "iscc_hub", verbosity=0)
        print("    Migrations created")
        return True
    else:
        print("  ℹ️  Using existing migrations")
        return False


def apply_migrations():
    # type: () -> None
    """Apply database migrations."""
    print("  ✓ Applying migrations...")
    call_command("migrate", verbosity=0)
    print("    Migrations applied")


def create_superuser():
    # type: () -> None
    """Create admin superuser account if it doesn't exist."""
    # Detect development environment same way as settings.py
    is_dev = (Path(__file__).parent.parent / "tests").exists()
    admin_password = os.environ.get("ISCC_HUB_ADMIN_PWD")

    if is_dev and not admin_password:
        # Development mode: create demo user for convenience
        print("  ✓ Creating demo superuser for development...")
        username = "demo"
        email = "demo@example.com"
        admin_password = "demo"
    elif admin_password:
        # Production/sandbox mode: use provided password
        print("  ✓ Creating admin superuser...")
        username = "admin"
        email = "admin@example.com"
    else:
        # No password and not dev mode: skip (safer for production)
        print("  ℹ️  Skipping superuser creation (ISCC_HUB_ADMIN_PWD not set)")
        return

    User = get_user_model()

    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email, password=admin_password)
        print(f"    Created superuser: {username}/{admin_password}")
    else:
        print(f"    Superuser '{username}' already exists")


def sync_hubs():
    # type: () -> None
    """Sync hub configurations from GitHub."""
    print("  ✓ Syncing hub list from GitHub...")
    call_command("sync_hubs", "--quiet", verbosity=0)
    print("    Hub list synchronized")


def load_fixtures():
    # type: () -> None
    """Load test fixture data if available."""
    fixtures_file = Path("iscc_hub/fixtures/test_data.json")
    if fixtures_file.exists():
        print("  ✓ Loading test fixtures...")
        call_command("loaddata", "test_data", verbosity=0)
        print(f"    Loaded fixtures from {fixtures_file}")
    else:
        print(f"  ⚠️  No fixtures found at {fixtures_file}")
        print("     Run 'uv run poe fixtures-generate' to create fixtures")


def cleanup_migrations(migrations_dir):
    # type: (Path) -> None
    """
    Clean up temporary migrations directory.

    :param migrations_dir: Path to migrations directory
    """
    if migrations_dir.exists():
        print("  ✓ Cleaning up temporary migrations...")
        try:
            import shutil

            shutil.rmtree(migrations_dir)
            print("    Migrations cleaned up")
        except Exception as e:
            print(f"    ⚠️  Could not clean up migrations: {e}")
            print("    You may need to manually delete iscc_hub/migrations/")


def print_summary():
    # type: () -> None
    """Print database summary and usage instructions."""
    print("\n📊 Database summary:")

    # Import models here to avoid issues if migrations don't exist yet
    from django.contrib.auth import get_user_model

    from iscc_hub.models import IsccDeclaration, LogRecord

    record_count = LogRecord.objects.count()
    declaration_count = IsccDeclaration.objects.count()
    active_count = IsccDeclaration.objects.filter(redacted=False).count()
    deletion_count = LogRecord.objects.filter(type=LogRecord.RecordType.DELETION).count()

    print(f"  - Log records: {record_count}")
    print(f"  - Declarations: {declaration_count}")
    print(f"    - Active: {active_count}")
    print(f"    - Deletions: {deletion_count}")

    print("\n🚀 You can now:")
    print("  - Run the dev server: uv run poe serve")
    print("  - Access admin at: http://localhost:8000/admin/")

    # Show current admin credentials based on what was created
    User = get_user_model()
    is_dev = (Path(__file__).parent.parent / "tests").exists()
    admin_password = os.environ.get("ISCC_HUB_ADMIN_PWD")

    if is_dev and not admin_password and User.objects.filter(username="demo").exists():
        print("\n🔐 Admin credentials:")
        print("  - Username: demo")
        print("  - Password: demo")
    elif admin_password and User.objects.filter(username="admin").exists():
        print("\n🔐 Admin credentials:")
        print("  - Username: admin")
        print(f"  - Password: {admin_password}")
    else:
        print("\n⚠️  No admin user created")


def init_database():
    # type: () -> None
    """
    Initialize database if it doesn't exist.

    Skips initialization if database already exists.
    """
    # Get database path from settings
    db_name = settings.DATABASES["default"]["NAME"]
    db_path = Path(db_name)

    if db_path.exists():
        print(f"ℹ️  Database already exists at: {db_path}")
        print("   Use 'uv run poe reset' to force reset the database")
        return

    print(f"🔄 Initializing development database: {db_path}")

    # Track if we created migrations (for cleanup later)
    created_migrations = ensure_migrations()

    # Apply migrations
    apply_migrations()

    # Create superuser
    create_superuser()

    # Load test fixtures
    load_fixtures()

    # Clean up migrations if we created them
    if created_migrations:
        migrations_dir = Path("iscc_hub/migrations")
        cleanup_migrations(migrations_dir)

    print("\n✅ Database initialization complete!")
    print_summary()


def reset_database():
    # type: () -> None
    """
    Reset the development database.

    Deletes existing database and recreates from scratch, then syncs the hub
    list from GitHub and loads test fixtures.
    """
    # Get database path from settings
    db_name = settings.DATABASES["default"]["NAME"]
    db_path = Path(db_name)

    print(f"🔄 Resetting development database: {db_path}")

    # Delete existing database if it exists
    if db_path.exists():
        delete_database(db_path)
    else:
        print("  ℹ️  No existing database found")

    # Track if we created migrations (for cleanup later)
    created_migrations = ensure_migrations()

    # Apply migrations
    apply_migrations()

    # Create superuser
    create_superuser()

    # Sync hub list from GitHub
    sync_hubs()

    # Load test fixtures
    load_fixtures()

    # Clean up migrations if we created them
    if created_migrations:
        migrations_dir = Path("iscc_hub/migrations")
        cleanup_migrations(migrations_dir)

    print("\n✅ Database reset complete!")
    print_summary()


def main():
    # type: () -> None
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/db_management.py [init|reset]")
        print("  init  - Initialize database if it doesn't exist")
        print("  reset - Force reset database (deletes existing)")
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        if command == "init":
            init_database()
        elif command == "reset":
            reset_database()
        else:
            print(f"Unknown command: {command}")
            print("Use 'init' or 'reset'")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during database operation: {e}")
        import traceback  # noqa: E402

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
