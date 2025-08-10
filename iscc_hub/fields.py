from django.db import models


class SequenceField(models.AutoField):
    """
    A primary key field that uses SQLite's rowid without AUTOINCREMENT.
    Provides gap-less sequence when used with proper transaction handling.

    Inherits from AutoField to get correct INSERT behavior from Django.
    """

    description = "Gap-less integer primary key"

    def db_type(self, connection):
        # type: (object) -> str
        """
        Return just INTEGER for SQLite to use rowid without AUTOINCREMENT.
        Django will automatically add PRIMARY KEY.
        """
        return "INTEGER"

    def db_type_suffix(self, connection):
        # type: (object) -> str
        """
        Override to return empty string instead of 'AUTOINCREMENT'.
        This ensures SQLite uses rowid without AUTOINCREMENT for gap-less sequences.
        """
        return ""
