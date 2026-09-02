#!/bin/bash
# EC2 user-data: provisions the news desk on first boot.
#
# Paste this into "Advanced details -> User data" when launching the
# instance. It installs everything, creates the service account, and
# leaves the desk STOPPED, because the secrets are not here and must not
# be: user-data is readable from the instance metadata endpoint by
# anything running on the box.
#
# Ubuntu 24.04 LTS, arm64 (t4g.small).
set -euxo pipefail

REPO="${REPO:-https://github.com/eoghanf17/Polybuyer.git}"
BRANCH="${BRANCH:-claude/profitable-traders-follow-ug123p}"
APP=/opt/polybuyer

apt-get update -y
apt-get install -y python3-venv python3-pip git

id -u newsdesk &>/dev/null || adduser --system --group --home "$APP" newsdesk
mkdir -p "$APP/data"

git clone --branch "$BRANCH" "$REPO" "$APP/src" || \
  (cd "$APP/src" && git fetch origin "$BRANCH" && git checkout "$BRANCH")

python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --upgrade pip
"$APP/.venv/bin/pip" install py-clob-client

install -m 644 "$APP/src/deploy/newsdesk.service" /etc/systemd/system/newsdesk.service

# Placeholder so the unit has something to read. Real values go in by hand.
if [ ! -f "$APP/.env" ]; then
  cat > "$APP/.env" <<'ENV'
# Fill these in, then: sudo systemctl start newsdesk
X_BEARER_TOKEN=
OPENAI_API_KEY=
POLY_PRIVATE_KEY=
NEWSDESK_DB=/opt/polybuyer/data/newsdesk.db
NEWSDESK_PAPER=1
NEWSDESK_MAX_DAILY_USD=100
ENV
fi

chown -R newsdesk:newsdesk "$APP"
chmod 600 "$APP/.env"
systemctl daemon-reload
systemctl enable newsdesk          # enabled, deliberately NOT started

echo "provisioned. add secrets to $APP/.env then: systemctl start newsdesk" \
  > /var/log/newsdesk-provision.done
