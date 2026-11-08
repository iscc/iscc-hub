---
icon: lucide/wrench
description: Back up, restore, upgrade and monitor a running hub
---

# Operations

A hub issues permanent identifiers. If you lose its data, you lose its log. Back up the data, upgrade with care and
monitor the hub.
{ .iscc-lead }

## Data

=== "SQLite"

    The hub keeps all its state in `/app/data`. Mount this directory on a persistent volume. It contains:

    | File                   | Contents                                                  |
    | ---------------------- | --------------------------------------------------------- |
    | `iscc-hub-<ID>.db`     | The database: log, declarations, admin users              |
    | `iscc-hub-<ID>.db-wal` | The write-ahead log of SQLite. It is part of the database |
    | `iscc-hub-<ID>.db-shm` | The shared memory file of SQLite                          |

    Do not copy these files while the hub runs. The copy can be damaged.

=== "PostgreSQL"

    The hub keeps all its state in its PostgreSQL database. The hub container has no state of its own. Keep the volume
    of the database container, or the storage of your database service.

## Back up

=== "SQLite"

    Make a backup while the hub runs with the backup function of SQLite. This example uses hub ID 42:

    ```bash
    docker compose exec iscc-hub python -c "import sqlite3;     sqlite3.connect('/app/data/iscc-hub-0042.db').backup(sqlite3.connect('/app/data/backup.db'))"
    docker compose cp iscc-hub:/app/data/backup.db ./iscc-hub-0042-$(date +%F).db
    docker compose exec iscc-hub rm /app/data/backup.db
    ```

    For continuous replication, use for example [Litestream](https://litestream.io/).

=== "PostgreSQL"

    Make a backup while the hub runs with `pg_dump`. With the PostgreSQL compose example from
    [Run a hub](run-a-hub.md#with-postgresql):

    ```bash
    docker compose exec -T db pg_dump -U iscc_hub -Fc iscc_hub > iscc-hub-$(date +%F).dump
    ```

    `pg_dump` makes a consistent copy while the hub writes. For continuous backups, use the point-in-time recovery of
    PostgreSQL or of your database service.

Keep copies on a different machine. Make a backup at least once a day and before each upgrade. Restore one backup on a
test machine to make sure that your backups work. A daily backup can lose up to one day of permanent ISCC-IDs, so use
continuous backups for a mainnet hub.

Also keep the signing key `ISCC_HUB_SECKEY`. If you lose it, the restored hub must use a new key, and nobody can verify
old receipts and checkpoints against its DID document anymore. Keep a copy of the key offline, in two safe places, and
not together with the database backups.

## Restore

=== "SQLite"

    This example restores the file `iscc-hub-0042-2026-11-08.db` from the current directory into the volume of hub 42:

    ```bash
    docker compose stop iscc-hub
    docker compose run --rm --no-deps --entrypoint sh         -v "$PWD/iscc-hub-0042-2026-11-08.db:/restore.db:ro" iscc-hub         -c 'rm -f /app/data/iscc-hub-0042.db-wal /app/data/iscc-hub-0042.db-shm && cp /restore.db /app/data/iscc-hub-0042.db'
    docker compose start iscc-hub
    ```

    The second command starts a temporary container on the same volume, without migrations and without the web
    server. It removes the old `-wal` and `-shm` files and copies the backup over the database.

=== "PostgreSQL"

    This example restores the file `iscc-hub-2026-11-08.dump`:

    ```bash
    docker compose stop iscc-hub
    docker compose exec -T db pg_restore -U iscc_hub -d iscc_hub --clean --if-exists --single-transaction         < iscc-hub-2026-11-08.dump
    docker compose start iscc-hub
    ```

    `--clean` replaces the tables of the hub with the tables from the backup. `--single-transaction` makes the restore
    all or nothing.

After the restore, check `/log/checkpoint`: the tree size is the size at the time of the backup.

!!! warning

    A backup does not contain the declarations that the hub accepted after the backup. Those ISCC-IDs and log entries are
    lost, but monitors and declarers already saw them. Monitors report the shorter log as an error. Back up often to keep
    this gap small.

## Upgrade

1. Read the [release notes](https://github.com/iscc/iscc-hub/releases) of each version after your current version.
2. Make a backup.
3. Change the image tag in `compose.yaml`, for example from `0.1.1` to the new version.
4. Run `docker compose pull` and `docker compose up -d`.
5. Check `/health`. It shows the new version.

The hub applies database migrations at start. Do not go back to an older version after a migration. Restore the backup
instead.

## Monitor

| Check                 | How                                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------- |
| The hub runs          | `GET /health` with `Accept: application/json` returns status 200 and `"status": "pass"`. The image has a Docker health check that uses it |
| Database and key work | `GET /log/checkpoint` returns status 200. It reads the database and signs with the key. `/health` checks neither |
| The log grows         | The second line of `GET /log/checkpoint` is the number of log entries                                     |
| The log is consistent | [ISCC Monitor](https://monitor.iscc.codes/) verifies the logs of all listed hubs                          |
| The clock is correct  | `timedatectl` shows `System clock synchronized: yes`. If the clock jumps back, the hub rejects declarations until the time catches up |
| Errors                | `docker compose logs iscc-hub`. Gunicorn writes access and error logs to the container output. Rotate them, see [Run a hub](run-a-hub.md#2-write-the-configuration) |

## Admin tasks

Open `https://<your domain>/admin/` and log in as `admin`.

| Task                         | How                                                                                                               |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Hide a malicious declaration | Under **Declarations**, set **Redacted**. The declaration no longer resolves on your hub. The log does not change |
| Accept only known keys       | Turn on [permissioned mode](configuration.md#permissioned-mode). Then add each allowed public key under **Public Keys** |

The admin interface cannot add, change or delete declarations. Only signed requests from declarers can do that.
