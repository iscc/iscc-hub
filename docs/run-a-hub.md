---
icon: lucide/server
description: Deploy your own hub with the container image, a reverse proxy and two secrets
---

# Run a hub

The hub is one container image. You need a server with Docker, a domain name and a reverse proxy for TLS.
{ .iscc-lead }

## Before you start

You need:

- A Linux server with Docker, 1 CPU and 2 GB of memory. The hub uses about 500 MB with the default 4 workers. On a
    server with 1 GB, set `WORKERS=2`.
- A local disk with 10 GB of free space. The database needs about 2 KB for each declaration. Do not put the data on
    NFS, SMB or a cloud file share: SQLite needs a local file system.
- A domain name for the hub, for example `hub.example.com`. The domain is part of the identity of the hub. Do not change
    it later.
- A reverse proxy that terminates TLS, for example Caddy, nginx or Traefik.
- A hub ID. Select a free hub ID in the hub list of your network. See [Join the network](join-the-network.md).

Make sure that:

- The server clock is synchronized. Each ISCC-ID contains the time of the hub, and wrong times stay in the IDs forever.
    On most Linux systems, `timedatectl` must show `System clock synchronized: yes`.
- The server can open outbound HTTPS connections to any public host. The hub downloads the hub list from GitHub, fetches
    the DID documents of declarers (DID verification policy) and sends searches to the search server. If the hub cannot
    fetch a DID document, it rejects the declaration.
- The domain points to the server before the reverse proxy requests a TLS certificate. Otherwise the certificate can be
    delayed by DNS caches and the limits of the certificate authority.

Decide on the network first:

| Network | `ISCC_HUB_REALM` | Use                                               |
| ------- | ---------------- | ------------------------------------------------- |
| testnet | `0`              | Tests and development. ISCC-IDs are not permanent |
| mainnet | `1`              | Production. ISCC-IDs are permanent                |

!!! warning "Fixed for the life of the hub"

    The hub ID, the realm, the signing key and the domain are fixed. Each ISCC-ID contains the hub ID and the realm. The key
    and the domain verify all receipts and checkpoints. If you change one of them, you must start a new hub with a new
    database.

## 1. Make the secrets

The hub needs two secrets. Make them one time.

Make the Ed25519 signing key of the hub:

```bash
uvx iscc-crypto keygen
```

The command prints a JSON object. `secret_key` is the value of `ISCC_HUB_SECKEY`. The `public_key` goes into the hub
list. The hub also publishes it at `https://<your domain>/.well-known/did.json`.

Keep a copy of the secret key offline, in two safe places. A database backup is useless without the key.

Make the Django secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 2. Write the configuration

Put the secrets into a `.env` file next to your compose file. Do not commit this file.

```bash title=".env"
DJANGO_SECRET_KEY=<the Django secret key>
ISCC_HUB_SECKEY=<the secret_key from iscc-crypto>
ISCC_HUB_ADMIN_PWD=<a password for the admin interface>
```

Write each comment in a `.env` file on its own line. `docker run --env-file` reads a comment after a value as part of
the value. The [`.env.example`](https://github.com/iscc/iscc-hub/blob/main/.env.example) file in the repository lists
all settings.

Write `compose.yaml`. Replace the domain and the hub ID:

```yaml title="compose.yaml"
services:
  iscc-hub:
    image: ghcr.io/iscc/iscc-hub:0.1.1
    restart: unless-stopped
    ports:
      - 127.0.0.1:8000:8000
    volumes:
      - iscc-hub-data:/app/data
      # Optional logo, see Configuration > Home page
      # - ./logo.svg:/app/iscc_hub/static/media/logo.svg:ro
    environment:
      DJANGO_DEBUG: "false"
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      ISCC_HUB_DOMAIN: hub.example.com
      ISCC_HUB_SECKEY: ${ISCC_HUB_SECKEY}
      ISCC_HUB_ID: "42"
      ISCC_HUB_REALM: "0"
      ISCC_HUB_ADMIN_PWD: ${ISCC_HUB_ADMIN_PWD}
      ISCC_HUB_SQLITE_SYNC_MODE: FULL
    # Gunicorn needs up to 30 seconds to finish open requests at shutdown
    stop_grace_period: 45s
    # Docker does not rotate container logs by default
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
volumes:
  iscc-hub-data:
```

Always use an exact version tag. Do not use `latest`, so that each upgrade is your decision. The
[Configuration](configuration.md) page lists all settings.

!!! warning "Keep the data volume"

    All state is in the volume on `/app/data`. Without a volume, the hub loses its log each time you recreate the
    container. Never change the volume, `ISCC_HUB_DB_ENGINE` or `ISCC_HUB_DB_NAME` after the first start. The hub would
    then start an empty log under the same identity.

## 3. Start the hub

```bash
docker compose up -d
docker compose logs -f iscc-hub
```

At each start, the container:

1. Applies the database migrations.
2. Makes the admin user `admin` if `ISCC_HUB_ADMIN_PWD` is set and the user does not exist.
3. Downloads the hub list of its realm from GitHub. If the download fails, the hub starts anyway and tries again later.
4. Starts the web server on port 8000.

## 4. Set up the reverse proxy

The container serves plain HTTP on port 8000. The reverse proxy must terminate TLS and send the original `Host` header.
If it sends a different host name, the hub answers with status 400.

The examples below are for a proxy on the host. If your proxy runs in a container, for example Traefik, put both
containers on one Docker network, remove `ports:` from `compose.yaml` and point the proxy at `iscc-hub:8000`.

=== "Caddy"

    Caddy sends the original `Host` header by default:

    ```text title="Caddyfile"
    hub.example.com {
        reverse_proxy 127.0.0.1:8000
    }
    ```

=== "nginx"

    nginx sends the upstream address as `Host` header by default. Set it to `$host`:

    ```nginx title="/etc/nginx/conf.d/iscc-hub.conf"
    server {
        listen 443 ssl;
        server_name hub.example.com;
        # ssl_certificate and ssl_certificate_key of your certificate

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
        }
    }
    ```

    To limit write requests (see below), add this to the `http` block:

    ```nginx
    map $request_method $hub_write { default ""; POST $binary_remote_addr; DELETE $binary_remote_addr; }
    limit_req_zone $hub_write zone=hub_writes:10m rate=30r/m;
    limit_req_status 429;
    ```

    And this location to the `server` block:

    ```nginx
    location /declaration {
        limit_req zone=hub_writes burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    ```

We also recommend these proxy rules:

- **Limit write requests.** The hub has no rate limit of its own. Declarations are permanent, and each new controller
    costs a DID fetch. Limit `POST` and `DELETE` requests to paths that start with `/declaration`, for each IP address,
    for example to 30 per minute. Answer with status 429. Do not limit reads or `/health`. nginx has `limit_req`. Caddy
    needs the `caddy-ratelimit` plugin.
- **Restrict the admin interface.** If you can, allow `/admin/` only from your own IP addresses or your VPN.

If the proxy must send a different host name, set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. See
[Configuration](configuration.md#web-and-proxy).

## 5. Check the hub

Do these checks from a different computer:

```bash
curl -H "Accept: application/json" https://hub.example.com/health
curl https://hub.example.com/.well-known/did.json
curl https://hub.example.com/log/checkpoint
```

- `/health` returns `"status": "pass"` and the version. Without the `Accept` header, it returns an HTML page.
- `/.well-known/did.json` contains the `public_key` from step 1.
- `/log/checkpoint` returns a signed checkpoint. A new hub has tree size 0.
- `docker compose ps` shows the container as `healthy`.

Then open `https://hub.example.com/admin/` and log in as `admin`.

## 6. Join the network

Other hubs and clients find your hub through the hub list. Add your hub to the list: see
[Join the network](join-the-network.md).

Then set up backups and monitoring: see [Operations](operations.md).

## With PostgreSQL

SQLite is the default and needs no other service. Use PostgreSQL if you already run it, or if your platform has no
persistent local disk. The hub is tested with PostgreSQL 16.

Add `POSTGRES_PASSWORD=<a long random password>` to your `.env` file. Then use this `compose.yaml` instead of the one in
step 2:

```yaml title="compose.yaml"
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: iscc_hub
      POSTGRES_USER: iscc_hub
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - iscc-hub-pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U iscc_hub -d iscc_hub"]
      interval: 10s
      timeout: 5s
      retries: 5
    stop_grace_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
  iscc-hub:
    image: ghcr.io/iscc/iscc-hub:0.1.1
    restart: unless-stopped
    # Start the hub only when the database accepts connections
    depends_on:
      db:
        condition: service_healthy
    ports:
      - 127.0.0.1:8000:8000
    environment:
      DJANGO_DEBUG: "false"
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      ISCC_HUB_DOMAIN: hub.example.com
      ISCC_HUB_SECKEY: ${ISCC_HUB_SECKEY}
      ISCC_HUB_ID: "42"
      ISCC_HUB_REALM: "0"
      ISCC_HUB_ADMIN_PWD: ${ISCC_HUB_ADMIN_PWD}
      ISCC_HUB_DB_ENGINE: postgres
      ISCC_HUB_DB_HOST: db
      ISCC_HUB_DB_USER: iscc_hub
      ISCC_HUB_DB_PASSWORD: ${POSTGRES_PASSWORD}
      ISCC_HUB_DB_NAME_PG: iscc_hub
    stop_grace_period: 45s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
volumes:
  iscc-hub-pg:
```

With PostgreSQL:

- All state is in the database. The hub container needs no volume. Keep the `iscc-hub-pg` volume.
- `ISCC_HUB_SQLITE_SYNC_MODE` and the local disk rule for `/app/data` do not apply. Keep the PostgreSQL defaults
    `fsync=on` and `synchronous_commit=on`, so that the database writes each declaration to disk before the hub confirms
    it.
- Use one database for each hub. Never let two hubs share one database.

To use a PostgreSQL server that you already have, or a managed database service:

1. Make a database and a user for the hub. Make the user the owner of the database, so that the hub can create its
   tables.
2. Set `ISCC_HUB_DB_HOST`, `ISCC_HUB_DB_PORT`, `ISCC_HUB_DB_USER`, `ISCC_HUB_DB_PASSWORD` and `ISCC_HUB_DB_NAME_PG`.
3. If the server requires TLS, also set `PGSSLMODE=verify-full` and, if needed, `PGSSLROOTCERT` with the path of the CA
   certificate in the container. The hub passes these standard PostgreSQL variables to the database driver.

The hub applies its migrations at the first start. [Operations](operations.md#back-up) describes backups with
`pg_dump`.

## Without Compose

```bash
docker run -d --name iscc-hub --restart unless-stopped \
    --env-file .env \
    -e DJANGO_DEBUG=false \
    -e ISCC_HUB_DOMAIN=hub.example.com \
    -e ISCC_HUB_ID=42 \
    -e ISCC_HUB_REALM=0 \
    -e ISCC_HUB_SQLITE_SYNC_MODE=FULL \
    -v iscc-hub-data:/app/data \
    -p 127.0.0.1:8000:8000 \
    --stop-timeout 45 \
    --log-driver json-file --log-opt max-size=10m --log-opt max-file=5 \
    ghcr.io/iscc/iscc-hub:0.1.1
```

## Build the image yourself

```bash
git clone https://github.com/iscc/iscc-hub
cd iscc-hub
git checkout v0.1.1
docker build --target production -t iscc-hub .
```
