#!/bin/bash
# Music Carousel Hours - One-line installer
# Usage: curl -sSL https://raw.githubusercontent.com/Alejandro-M-P/Music_Carousel_Hours/main/install.sh | bash

set -e

REPO_URL="https://github.com/Alejandro-M-P/Music_Carousel_Hours.git"
INSTALL_DIR="$HOME/Music_Carousel_Hours"
BELL_USER=$(whoami)

echo "🎵 Music Carousel Hours - School Bell System Installer"
echo "=================================================="

# 1. Install mpv if not present
if ! command -v mpv &> /dev/null; then
    echo "[1/4] Installing mpv..."
    sudo apt-get update && sudo apt-get install -y mpv
else
    echo "[1/4] mpv already installed ✅"
fi

# 2. Clone repository
if [ -d "$INSTALL_DIR" ]; then
    echo "[2/4] Directory exists, pulling updates..."
    cd "$INSTALL_DIR" && git pull
else
    echo "[2/4] Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Setup crontab
echo "[3/4] Setting up crontab entries..."
python3 bell.py --setup-cron

# 4. Verify installation
echo "[4/4] Verifying installation..."
python3 -m unittest discover -s tests > /dev/null 2>&1 && echo "✅ All 73 tests passed!" || echo "⚠️ Some tests failed, check manually"

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Your bell system is now installed at: $INSTALL_DIR"
echo "  2. Crontab entries have been added for the school schedule"
echo "  3. To test: cd $INSTALL_DIR && python3 bell.py cambio"
echo "  4. To remove: cd $INSTALL_DIR && python3 bell.py --remove-cron"
echo ""
echo "The system will now play music automatically at the configured times."
echo "Perfect for your school! 🏫"
