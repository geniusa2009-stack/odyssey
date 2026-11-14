#!/usr/bin/env bash
# Sets up an Ubuntu 22.04 NVIDIA GPU host (e.g. AWS g4dn.xlarge, T4) to stream an ODYSSEY Linux
# package with Pixel Streaming 2: backend (mock AI, SQLite) on 127.0.0.1:8000, the game rendering
# off-screen, the Wilbur signalling server, coturn (TURN over UDP/TCP 3478 and TLS 5349) and Caddy
# serving the player page over HTTPS with an automatic certificate.
#
#   sudo PACKAGE=/opt/odyssey/odyssey-linux-....tar.gz BACKEND_DIR=/opt/odyssey/backend \
#        STREAM_HOST=203-0-113-10.sslip.io ACCESS_PASSWORD='...' ./setup_stream_host.sh
#
# STREAM_HOST: a DNS name resolving to this host (a free <ip-with-dashes>.sslip.io name works).
# ACCESS_PASSWORD (optional): puts HTTP basic auth (user "judge") in front of the stream.
# Security group / firewall: open TCP 80, 443, 3478, 5349 and UDP 3478 + 49152-65535 only.
# Secrets (TURN password, access hash) are generated on the host and never committed.
set -euo pipefail
: "${PACKAGE:?path to odyssey-linux-*.tar.gz}" "${BACKEND_DIR:?path to the backend source (Dockerfile)}"
: "${STREAM_HOST:?public DNS name of this host}"
ROOT=/opt/odyssey
PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com || hostname -I | awk '{print $1}')"
nvidia-smi >/dev/null || { echo "NVIDIA driver missing: install the driver for this GPU first" >&2; exit 1; }

apt-get update -y
apt-get install -y coturn docker.io curl unzip libvulkan1 vulkan-tools pulseaudio debian-keyring \
  debian-archive-keyring apt-transport-https gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' >/etc/apt/sources.list.d/caddy-stable.list
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y caddy nodejs
id odyssey >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin odyssey

# Versioned game install; "current" is a symlink, so rollback = repoint it and restart odyssey-game
VERSION="$(basename "$PACKAGE" .tar.gz)"
mkdir -p "$ROOT/releases/$VERSION"
tar -C "$ROOT/releases/$VERSION" -xzf "$PACKAGE"
ln -sfn "$ROOT/releases/$VERSION" "$ROOT/current"
chown -R odyssey:odyssey "$ROOT/releases"

# Signalling server (Pixel Streaming Infrastructure, branch matching UE 5.8)
if [[ ! -d "$ROOT/ps-infra" ]]; then
  curl -fsSL https://github.com/EpicGamesExt/PixelStreamingInfrastructure/archive/refs/heads/UE5.8.tar.gz \
    | tar -xz -C "$ROOT" && mv "$ROOT/PixelStreamingInfrastructure-UE5.8" "$ROOT/ps-infra"
  chown -R odyssey:odyssey "$ROOT/ps-infra"
fi
# Epic's own setup: installs deps, builds the libraries, Wilbur and the TypeScript player page (www)
sudo -u odyssey -H bash "$ROOT/ps-infra/SignallingWebServer/platform_scripts/bash/setup.sh" --build
[[ -f $ROOT/ps-infra/SignallingWebServer/dist/index.js && -d $ROOT/ps-infra/SignallingWebServer/www ]] \
  || { echo "signalling build incomplete (dist/index.js or www missing)" >&2; exit 1; }

# TURN relay with a generated long-term credential
TURN_PASS_FILE=/etc/odyssey/turn.pass
mkdir -p /etc/odyssey && chmod 700 /etc/odyssey
[[ -s $TURN_PASS_FILE ]] || head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' >"$TURN_PASS_FILE"
TURN_PASS="$(cat "$TURN_PASS_FILE")"
cat >/etc/turnserver.conf <<EOF
listening-port=3478
tls-listening-port=5349
external-ip=$PUBLIC_IP
realm=$STREAM_HOST
fingerprint
lt-cred-mech
user=odyssey:$TURN_PASS
min-port=49152
max-port=65535
no-cli
no-multicast-peers
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
EOF
sed -i 's/^#\?TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn || true
PEER_OPTIONS="{\"iceServers\":[{\"urls\":[\"stun:$STREAM_HOST:3478\"]},{\"urls\":[\"turn:$STREAM_HOST:3478?transport=udp\",\"turn:$STREAM_HOST:3478?transport=tcp\"],\"username\":\"odyssey\",\"credential\":\"$TURN_PASS\"}]}"
printf 'PEER_OPTIONS=%s\n' "$PEER_OPTIONS" >/etc/odyssey/signalling.env
chmod 600 /etc/odyssey/signalling.env

# Backend (mock AI, SQLite, no external services), bound to localhost only
docker build -t odyssey-backend:local "$BACKEND_DIR"
docker rm -f odyssey-backend >/dev/null 2>&1 || true
docker run -d --name odyssey-backend --restart unless-stopped -p 127.0.0.1:8000:8000 \
  -e ODYSSEY_ENVIRONMENT=development -e ODYSSEY_AUTO_CREATE_SCHEMA=true -e ODYSSEY_AI_PROVIDER=mock \
  -e ODYSSEY_DATABASE_URL=sqlite+aiosqlite:////tmp/odyssey.db odyssey-backend:local

cat >/etc/systemd/system/odyssey-signalling.service <<EOF
[Unit]
Description=ODYSSEY Pixel Streaming 2 signalling (Wilbur)
After=network-online.target
[Service]
User=odyssey
EnvironmentFile=/etc/odyssey/signalling.env
Environment=PATH=$ROOT/ps-infra/SignallingWebServer/platform_scripts/bash/node/bin:/usr/bin:/bin
WorkingDirectory=$ROOT/ps-infra/SignallingWebServer
ExecStart=/usr/bin/env node dist/index.js --serve --http_root $ROOT/ps-infra/SignallingWebServer/www --player_port 8080 --streamer_port 8888 --peer_options \${PEER_OPTIONS}
Restart=always
[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/odyssey-game.service <<EOF
[Unit]
Description=ODYSSEY game (off-screen, Pixel Streaming 2)
After=odyssey-signalling.service docker.service
Requires=odyssey-signalling.service
[Service]
User=odyssey
WorkingDirectory=$ROOT/current
ExecStart=$ROOT/current/Odyssey.sh -RenderOffscreen -ForceRes -ResX=1920 -ResY=1080 -PixelStreamingURL=ws://127.0.0.1:8888 -AllowPixelStreamingCommands=false -Unattended -log
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# HTTPS front door (automatic certificate); optional basic auth for judges
AUTH=""
if [[ -n "${ACCESS_PASSWORD:-}" ]]; then
  AUTH="basic_auth {
		judge $(caddy hash-password --plaintext "$ACCESS_PASSWORD")
	}"
fi
cat >/etc/caddy/Caddyfile <<EOF
$STREAM_HOST {
	encode gzip
	$AUTH
	reverse_proxy 127.0.0.1:8080
	header Strict-Transport-Security "max-age=31536000"
}
EOF

systemctl daemon-reload
systemctl enable --now coturn odyssey-signalling odyssey-game
systemctl restart caddy coturn
echo "stream: https://$STREAM_HOST  (release $VERSION)"
