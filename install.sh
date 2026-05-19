#!/usr/bin/env bash
# photopainter install script — Raspberry Pi OS Lite 64-bit (Bookworm / Trixie).
# Run on a freshly-imaged Pi:
#   git clone https://github.com/<you>/photopainter.git
#   cd photopainter
#   sudo ./install.sh
#
# Idempotent: safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$USER}"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo)." >&2
    exit 1
fi

echo "==> Installing photopainter as user '$USER_NAME' from $REPO_DIR"

# --- 0. SD sanity check (warning only) ---
if [[ -f /sys/block/mmcblk0/device/manfid ]]; then
    manfid="$(cat /sys/block/mmcblk0/device/manfid)"
    if [[ "$manfid" == "0x000000" ]]; then
        echo "WARNING: SD manfid is 0x000000 (likely counterfeit). Real IDs: 0x1b Samsung, 0x03 SanDisk, 0x27 Kingston, 0x28 Lexar."
        echo "Continuing, but ext4 corruption is likely."
        sleep 3
    fi
fi

# --- 1. SPI ---
raspi-config nonint do_spi 0 || true

# --- 2. APT deps ---
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    python3-pil python3-numpy python3-pydantic python3-spidev \
    python3-gpiozero python3-yaml python3-requests python3-rpi-lgpio \
    python3-flask gunicorn \
    git logrotate

# --- 3. Waveshare e-Paper lib + PWR_PIN patch ---
EPAPER_DIR=/opt/e-Paper
if [[ ! -d "$EPAPER_DIR" ]]; then
    git clone --depth 1 https://github.com/waveshareteam/e-Paper.git "$EPAPER_DIR"
    rm -rf "$EPAPER_DIR/Arduino" "$EPAPER_DIR/Arduino_R4" \
           "$EPAPER_DIR/STM32" "$EPAPER_DIR/E-paper_Separate_Program" "$EPAPER_DIR/.git" || true
fi
# PhotoPainter ACCE uses GPIO 27 for PWR, the upstream lib defaults to GPIO 18.
sed -i 's/PWR_PIN  = 18/PWR_PIN  = 27/g' \
    "$EPAPER_DIR/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py"

PY_VER="$(python3 -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
PTH_DIR="/usr/local/lib/${PY_VER}/dist-packages"
mkdir -p "$PTH_DIR"
echo "$EPAPER_DIR/RaspberryPi_JetsonNano/python/lib" > "$PTH_DIR/waveshare-epd.pth"

# --- 4. Code -> /opt/photopainter ---
mkdir -p /opt/photopainter
cp -r "$REPO_DIR/photopainter" /opt/photopainter/
cp "$REPO_DIR/refresh.sh" /opt/photopainter/
cp "$REPO_DIR/config.yaml.example" /opt/photopainter/
chmod +x /opt/photopainter/refresh.sh
chown -R "$USER_NAME:$USER_NAME" /opt/photopainter

# --- 5. System directories ---
mkdir -p /etc/photopainter /var/lib/photopainter /var/log/photopainter \
         /var/cache/photopainter /run/photopainter
chown "$USER_NAME:$USER_NAME" /etc/photopainter /var/lib/photopainter \
    /var/log/photopainter /var/cache/photopainter /run/photopainter

# --- 6. Initial config (do not overwrite) ---
if [[ ! -f /etc/photopainter/config.yaml ]]; then
    cp "$REPO_DIR/config.yaml.example" /etc/photopainter/config.yaml
    chown "$USER_NAME:$USER_NAME" /etc/photopainter/config.yaml
    chmod 640 /etc/photopainter/config.yaml
fi

# --- 7. systemd unit ---
sed "s/^User=.*/User=$USER_NAME/; s/^Group=.*/Group=$USER_NAME/" \
    "$REPO_DIR/systemd/photopainter-web.service" \
    > /etc/systemd/system/photopainter-web.service
systemctl daemon-reload
systemctl enable photopainter-web.service

# --- 8. Crontab (5-min ticks, nightly cache purge, refresh at boot) ---
CRON_REFRESH='*/5 6-23 * * * /opt/photopainter/refresh.sh >> /var/log/photopainter/cron.log 2>&1'
CRON_PURGE='0 0 * * * cd /opt/photopainter && /usr/bin/python3 -m photopainter --purge-cache >> /var/log/photopainter/cron.log 2>&1'
CRON_BOOT='@reboot sleep 30 && /opt/photopainter/refresh.sh --ignore-schedule >> /var/log/photopainter/cron.log 2>&1'
(sudo -u "$USER_NAME" crontab -l 2>/dev/null \
    | grep -vE 'photopainter/refresh.sh|--purge-cache' ;
 echo "$CRON_REFRESH" ; echo "$CRON_PURGE" ; echo "$CRON_BOOT") \
    | sudo -u "$USER_NAME" crontab -

# --- 9. logrotate ---
cat > /etc/logrotate.d/photopainter <<EOF
/var/log/photopainter/*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    create 0640 $USER_NAME $USER_NAME
}
EOF

# --- 10. Allow gunicorn to bind on port 80 without root ---
# (already in the systemd unit via AmbientCapabilities)

# --- 11. Start ---
systemctl start photopainter-web.service
sleep 2

HOST="$(hostname)"
IP="$(hostname -I | awk '{print $1}')"

if ! systemctl is-active --quiet photopainter-web.service; then
    echo "WARNING: photopainter-web.service did not start. Check 'journalctl -u photopainter-web -n 50'."
fi

echo
echo "===================================================================="
echo " photopainter installed."
echo
echo " Open the web UI from any device on your LAN:"
echo "   http://${HOST}.local/      (mDNS)"
echo "   http://${IP}/              (direct IP)"
echo
echo " Fill in the Immich URL + API key, pick an album, save."
echo "===================================================================="
