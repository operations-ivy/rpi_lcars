#!/bin/sh
# Set up the LCARS panel on brick1982, in place of brick-arena's kiosk. Run on
# brick1982 itself, from the git clone at ~/rpi_lcars. After this,
# lcars-deploy.timer keeps it up to date from GitHub.
set -eu
here=$(cd "$(dirname "$0")" && pwd)

# pygame and friends from Debian (no venv to build on the Pi); cage is the
# compositor; grim takes screenshots of the panel for checking it remotely.
sudo apt-get install -y --no-install-recommends cage grim \
    python3-pygame python3-psutil python3-pil python3-pytest

mkdir -p ~/.config/lcars ~/.config/systemd/user
if [ ! -f ~/.config/lcars/env ]; then
    install -m 600 "$here/lcars.env.example" ~/.config/lcars/env
fi
cp "$here/lcars-deploy.service" "$here/lcars-deploy.timer" ~/.config/systemd/user/

sudo cp "$here/90-backlight.rules" /etc/udev/rules.d/
sudo udevadm trigger --subsystem-match=backlight --action=add
sudo python3 "$here/blank-cursors" /usr/local/share/lcars/cursors/default
sudo cp "$here/lcars-kiosk.service" /etc/systemd/system/

# brick-arena's kiosk and daemon step aside (brick-cicd-config retires them).
sudo systemctl disable --now brick-kiosk.service 2>/dev/null || true
systemctl --user disable --now brick-arena.service 2>/dev/null || true

sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now lcars-deploy.timer
sudo systemctl daemon-reload
sudo systemctl disable getty@tty1.service
sudo systemctl enable lcars-kiosk.service
sudo systemctl set-default graphical.target
sudo systemctl restart lcars-kiosk.service
echo "LCARS panel installed; the kiosk is on tty1 (journalctl -u lcars-kiosk)."
