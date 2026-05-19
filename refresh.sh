#!/bin/bash
# /opt/photopainter/refresh.sh — invoqué par cron tous les 5min, et par le backend web.
# Idempotent : exit 0 silencieux si hors plage horaire OU intervalle pas écoulé.
set -euo pipefail
cd /opt/photopainter
exec python3 -m photopainter "$@"
