#!/usr/bin/env bash
# Repair nginx reverse proxy for myhigh5.com (ports 80/443 → :3000 / :8001).
# Run ON THE VPS as root: bash scripts/fix_nginx_myhigh5.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="${MH5_DOMAIN:-myhigh5.com}"
SITE_AVAILABLE="/etc/nginx/sites-available/${DOMAIN}"
SITE_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
FRONTEND_PORT="${MH5_FRONTEND_PORT:-3000}"
BACKEND_PORT="${MH5_BACKEND_PORT:-8001}"
MEDIA_ROOT="${MH5_MEDIA_ROOT:-/var/lib/myhigh5/media}"

if [ -f "${ROOT}/backend/.env" ]; then
  _env_media="$(grep -E '^LOCAL_STORAGE_PATH=' "${ROOT}/backend/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"'"' || true)"
  if [ -n "${_env_media}" ]; then
    MEDIA_ROOT="${_env_media}"
  fi
fi
mkdir -p "${MEDIA_ROOT}"

echo "=== fix nginx for ${DOMAIN} (media root: ${MEDIA_ROOT}) ==="

if ! command -v nginx >/dev/null 2>&1; then
  echo "    installing nginx..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
fi

echo ""
echo "=== listeners before fix ==="
ss -ltnp 2>/dev/null | grep -E ':80 |:443 ' || echo "(nothing on :80 or :443)"

echo ""
echo "=== local app health ==="
curl -sf "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null \
  && echo "    frontend :${FRONTEND_PORT} OK" \
  || echo "    FAIL frontend :${FRONTEND_PORT} — run: bash scripts/restart_mh5_frontend.sh"
curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/v1/build-info" >/dev/null \
  && echo "    backend  :${BACKEND_PORT} OK" \
  || echo "    FAIL backend :${BACKEND_PORT} — run: bash scripts/restart_mh5_backend.sh"

HAS_SSL=0
if [ -f "${CERT_DIR}/fullchain.pem" ] && [ -f "${CERT_DIR}/privkey.pem" ]; then
  HAS_SSL=1
  echo "    SSL certs found at ${CERT_DIR}"
else
  echo "    WARN: no Let's Encrypt certs at ${CERT_DIR}"
  if command -v certbot >/dev/null 2>&1; then
    echo "    try: certbot certonly --nginx -d ${DOMAIN} -d www.${DOMAIN}"
  fi
fi

echo ""
echo "=== write ${SITE_AVAILABLE} ==="
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

if [ "$HAS_SSL" -eq 1 ]; then
  cat >"$SITE_AVAILABLE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN} www.${DOMAIN};

    ssl_certificate     ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 64M;

    location ~ ^/api/v1/media/file/([0-9]+)/(.+)$ {
        alias ${MEDIA_ROOT}/\$1/\$2;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=86400";
        add_header Access-Control-Allow-Origin "*";
    }

    location ^~ /_next/ {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /media/ {
        alias ${MEDIA_ROOT}/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=86400";
        add_header Access-Control-Allow-Origin "*";
    }

    location / {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX
else
  # Temporary HTTP-only so the site is reachable while SSL is renewed.
  cat >"$SITE_AVAILABLE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    client_max_body_size 64M;

    location ~ ^/api/v1/media/file/([0-9]+)/(.+)$ {
        alias ${MEDIA_ROOT}/\$1/\$2;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=86400";
        add_header Access-Control-Allow-Origin "*";
    }

    location ^~ /_next/ {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /media/ {
        alias ${MEDIA_ROOT}/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=86400";
        add_header Access-Control-Allow-Origin "*";
    }

    location / {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX
fi

ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

echo ""
echo "=== firewall (ufw) ==="
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  ufw status 2>/dev/null | head -20 || true
else
  echo "    ufw not installed (check Hostinger hPanel firewall for ports 80/443)"
fi

echo ""
echo "=== nginx test + restart ==="
nginx -t
systemctl enable nginx
systemctl restart nginx
sleep 1
systemctl is-active nginx && echo "    nginx: active" || {
  journalctl -u nginx -n 30 --no-pager
  exit 1
}

echo ""
echo "=== listeners after fix ==="
ss -ltnp 2>/dev/null | grep -E ':80 |:443 ' || echo "(still nothing on :80/:443 — check Hostinger firewall)"

echo ""
echo "=== via nginx (localhost) ==="
curl -sS -o /dev/null -w "    http://127.0.0.1/ → HTTP %{http_code}\n" -H "Host: ${DOMAIN}" http://127.0.0.1/ || true
if [ "$HAS_SSL" -eq 1 ]; then
  curl -skS -o /dev/null -w "    https://127.0.0.1/ → HTTP %{http_code}\n" -H "Host: ${DOMAIN}" https://127.0.0.1/ || true
fi

echo ""
echo "=== public check ==="
if [ "$HAS_SSL" -eq 1 ]; then
  curl -sf "https://${DOMAIN}/api/v1/build-info" && echo "" || echo "    FAIL https://${DOMAIN} from VPS"
else
  curl -sf "http://${DOMAIN}/api/v1/build-info" && echo "" || echo "    FAIL http://${DOMAIN} from VPS"
  echo ""
  echo "    Renew HTTPS: certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}"
fi

echo ""
echo "If public still fails but localhost works:"
echo "  → Open ports 80 and 443 in Hostinger VPS → Firewall / Security panel"
echo "  → journalctl -u nginx -n 50 --no-pager"
