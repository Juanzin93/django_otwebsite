#!/usr/bin/env bash
set -euo pipefail

### ========= CONFIGURE ME =========
# Domain / site
DOMAIN="retrowarot.com"                   # e.g. retrowarot.com (for HTTPS & ALLOWED_HOSTS)
SERVER_ADMIN="admin@${DOMAIN}"
DEPLOY_USER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"
# Where to deploy
APP_ROOT="/srv/django_otwebsite"          # deployment root
DJANGO_DIR="otserver"                     # folder containing manage.py
WSGI_MODULE="main.wsgi"                   # dotted wsgi module path

# Your git repo (https or ssh)
REPO_URL="https://github.com/Juanzin93/django_otwebsite.git"

# Database (created locally)
DB_NAME="retrowar"
DB_USER="juanzin"
DB_PASS="rionovo123"

# Django admin (optional auto-create)
ADMIN_USER="juanzin"
ADMIN_EMAIL="admin@${DOMAIN}"
ADMIN_PASS="rionovo123"     # will set after createsuperuser --noinput

# Python version (system default 3.10 is fine on 22.04)
PY="python3"

# Enable Let's Encrypt auto-HTTPS? (yes/no)
ENABLE_HTTPS="yes"
### ========= END CONFIG =========

echo "==> Updating apt & installing system packages"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  apache2 libapache2-mod-wsgi-py3 \
  mysql-server \
  ${PY}-venv ${PY}-dev build-essential pkg-config \
  default-libmysqlclient-dev curl git

echo "==> Ensuring Apache allowed in UFW (if enabled)"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "Apache Full" || true
fi

echo "==> Securing MySQL (non-interactive baseline)"
# If mysql_secure_installation already run, these won’t harm.
mysql --protocol=socket -uroot <<SQL || true
DELETE FROM mysql.user WHERE User='';
DROP DATABASE IF EXISTS test;
DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';
FLUSH PRIVILEGES;
SQL

echo "==> Creating database & user (if not exist)"
mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "==> Preparing app directory: ${APP_ROOT}"
mkdir -p "${APP_ROOT}"
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "${APP_ROOT}"
cd "${APP_ROOT}"

if [ ! -d .git ]; then
  echo "==> Cloning repo: ${REPO_URL}"
  sudo -u "$DEPLOY_USER" git clone "${REPO_URL}" .
else
  echo "==> Repo exists, pulling latest"
  sudo -u "$DEPLOY_USER" git pull --rebase
fi

echo "==> Creating virtualenv"
${PY} -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
python -m pip install -U django-tinymce
echo "==> Installing Python deps"
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  # minimal safe set if no requirements.txt
  pip install Django==5.2.6 mysqlclient
fi

echo "==> Writing .env under ${DJANGO_DIR}/ (settings expect BASE_DIR/.env)"
SECRET_KEY="$(openssl rand -hex 32)"
ENV_PATH="${APP_ROOT}/${DJANGO_DIR}/.env"
cat > "${ENV_PATH}" <<ENV
# --- Database ---# 
#.env file for django_otwebsite/otserver
DEFAULT_FROM_EMAIL=Retrowar OT <no-reply@retrowarot.com>
SUPPORT_EMAIL=support@retrowarot.com

# EXPORT ON LINUX/UNIX SYSTEMS USING:
# export VARIABLE_NAME="value"
GRAPH_TENANT_ID="3680d58b-1126-4127-94ca-38e4553ab6dd"
GRAPH_CLIENT_ID="3085c801-db9a-4e43-a507-303ead6200cd"
GRAPH_CLIENT_SECRET=""
GRAPH_SENDER="retro@retrowarot.com"
EMAIL_BACKEND="pages.mail_backends.GraphEmailBackend"

# Database configuration
DB_NAME=retrowar
DB_USER=juanzin
DB_PASSWORD=rionovo123
DB_HOST=127.0.0.1
DB_PORT=3306

# ---- Stripe ----
STRIPE_API_KEY=""
STRIPE_PUBLIC_KEY=""
STRIPE_WEBHOOK_SECRET=""
STRIPE_PIX_ENABLED=0
# Map your Stripe Price IDs per pack/currency (already referenced in the view via env)
# Example (place into your environment):
STRIPE_PRICE_USD_C25=price_1SBg0tP5F3OJyKcMrscbWWMu
STRIPE_PRICE_BRL_C25=price_1SBgmcP5F3OJyKcMaxOd4Avy
STRIPE_PRICE_USD_C50=price_1SBhMyP5F3OJyKcMr9DBcmsQ
STRIPE_PRICE_BRL_C50=price_1SBhDhP5F3OJyKcMOKJdOdGd
STRIPE_PRICE_USD_C100=price_1SD9OyP5F3OJyKcMqm2cjK9P
STRIPE_PRICE_BRL_C100=price_1SBhEOP5F3OJyKcMyQcg23NA
STRIPE_PRICE_USD_C250=price_1SD9PwP5F3OJyKcM3BDc1Eey
STRIPE_PRICE_BRL_C250=price_1SBhGYP5F3OJyKcMKHWy7eou
STRIPE_PRICE_USD_C550=price_1SD9ROP5F3OJyKcMFuoSuJTX
STRIPE_PRICE_BRL_C550=price_1SD9T0P5F3OJyKcMNyACCdjt
STRIPE_PRICE_USD_C1100=price_1SD9SBP5F3OJyKcMygy8lgXT
STRIPE_PRICE_BRL_C1100=price_1SD9RpP5F3OJyKcMB2bPaNay

# ---- PayPal ----
PAYPAL_CLIENT_ID=0
PAYPAL_SECRET=0
PAYPAL_ENV="sandbox"

# Use "production" or "sandbox"
EFI_ENV=production

# ---- PIX (manual fallback) ----
PIX_KEY=""
PIX_QR_IMAGE=""

# ---- Optional site name (used in PayPal context)
SITE_NAME="Retrowar OT"

# Enable or disable features by setting the corresponding variable to true or false

# Left-side menu
SHOP_ENABLED=true

# Right-side menu
QUICKLOGIN_SHOWBOX_ENABLED=true
GALLERY_SHOWBOX_ENABLED=true
SERVERINFO_SHOWBOX_ENABLED=true
CHARMARKET_SHOWBOX_ENABLED=true
POWERGAMERS_SHOWBOX_ENABLED=false
ONLINERANKING_SHOWBOX_ENABLED=false
DISCORDWIDGET_ENABLED=false

# OT players table + key columns
OT_PLAYERS_TABLE="players"
OT_PLAYERS_ACCOUNT_COL="account_id"
OT_DEFAULT_TOWN_ID=11
OT_START_LEVEL=1
OT_START_HEALTH=150
OT_START_MANA=0
OT_START_CAP=400
OT_START_MAGLEVEL=0
OT_START_SOUL=100
OT_START_POSX=32097
OT_START_POSY=32219
OT_START_POSZ=7
OT_START_LOOKTYPE_MALE=128
OT_START_LOOKTYPE_FEMALE=136
OT_START_LOOKHEAD=78
OT_START_LOOKBODY=88
OT_START_LOOKLEGS=58
OT_START_LOOKFEET=0
ENV

echo "==> Ensuring STATIC_ROOT and API folders exist"
STATIC_ROOT="${APP_ROOT}/${DJANGO_DIR}/static_collected"
mkdir -p "${STATIC_ROOT}"
# *** NEW: Ensure API folder exists for OTClient updater downloads ***
API_DIR="${APP_ROOT}/${DJANGO_DIR}/api"
mkdir -p "${API_DIR}"
chown -R www-data:www-data "${API_DIR}" || true

echo "==> Running Django migrate & collectstatic"
cd "${APP_ROOT}/${DJANGO_DIR}"
# Safety: ensure production flags exist in your settings.py:
#   DEBUG=False, ALLOWED_HOSTS includes ${DOMAIN}, STATIC_ROOT points to static_collected
python manage.py migrate
python manage.py collectstatic --noinput

echo "==> Creating superuser (non-interactive)"
python manage.py createsuperuser --noinput --username "${ADMIN_USER}" --email "${ADMIN_EMAIL}" || true
python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE","main.settings")
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(username="admin", defaults={"email":"admin@retrowarot.com"})
u.set_password("rionovo123")
u.is_staff = True
u.is_superuser = True
u.save()
print("Superuser ensured. Created:", created)
PY

echo "==> Apache vhost configuration"
SITE_CONF="/etc/apache2/sites-available/otwebsite.conf"
cat > "${SITE_CONF}" <<APACHE
<VirtualHost *:80>
    ServerName ${DOMAIN}
    ServerAdmin ${SERVER_ADMIN}

    # Django via mod_wsgi (daemon mode)
    WSGIDaemonProcess otwebsite python-home=${APP_ROOT}/.venv \\
        python-path=${APP_ROOT}/${DJANGO_DIR}
    WSGIProcessGroup otwebsite
    WSGIScriptAlias / ${APP_ROOT}/${DJANGO_DIR}/${WSGI_MODULE}.py

    <Directory ${APP_ROOT}/${DJANGO_DIR}/main>
        <Files wsgi.py>
            Require all granted
        </Files>
    </Directory>

    # Static files (collected)
    Alias /static/ ${STATIC_ROOT}/
    <Directory ${STATIC_ROOT}>
        Require all granted
    </Directory>

    # *** NEW: Raw file server for OTClient updater (/api) ***
    Alias /api/ ${API_DIR}/
    <Directory ${API_DIR}/>
        Options -Indexes
        Require all granted
        # Optional: basic caching for static payloads
        <IfModule mod_headers.c>
            Header set Cache-Control "public, max-age=3600, immutable"
        </IfModule>
    </Directory>

    # If you have media, uncomment:
    # Alias /media/ ${APP_ROOT}/${DJANGO_DIR}/media/
    # <Directory ${APP_ROOT}/${DJANGO_DIR}/media>
    #     Require all granted
    # </Directory>

    ErrorLog \${APACHE_LOG_DIR}/otwebsite_error.log
    CustomLog \${APACHE_LOG_DIR}/otwebsite_access.log combined
</VirtualHost>
APACHE

echo "==> Enabling site & modules"
a2enmod wsgi headers >/dev/null
a2ensite otwebsite >/dev/null || true
a2dissite 000-default >/dev/null || true
systemctl reload apache2

if [ "${ENABLE_HTTPS}" = "yes" ]; then
  echo "==> Installing & running certbot for HTTPS"
  apt-get install -y certbot python3-certbot-apache
  certbot --apache -d "${DOMAIN}" --non-interactive --agree-tos -m "${SERVER_ADMIN}" || true
fi

echo "==> Done!"
echo "Visit:  http://${DOMAIN}/    (or server IP)"
echo "Admin:  http://${DOMAIN}/admin/   user: ${ADMIN_USER}"
echo "OTClient files URL base: http://${DOMAIN}/api/"
