#!/usr/bin/env bash
# Bootstrap all vendor submodules required to build Wavy Labs.
# Run once after cloning: ./vendor/bootstrap.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Initialising git submodules …"
git submodule update --init --recursive

echo ""
echo "Checking Python AI backend deps …"
if command -v python3 &>/dev/null; then
    python3 -m pip install --quiet --upgrade pip
    python3 -m pip install -r wavy-ai/requirements.txt
    echo "  Python deps installed."
else
    echo "  WARNING: python3 not found. Install Python 3.10+ and re-run."
fi

echo ""
echo "Checking ACE-Step …"
if [ ! -d "$ROOT/vendor/ACE-Step" ]; then
    git clone https://github.com/ace-step/ACE-Step.git vendor/ACE-Step
    pip install -e vendor/ACE-Step
    echo "  ACE-Step installed."
else
    echo "  ACE-Step already present."
fi

echo ""
echo "Checking DiffRhythm …"
if [ ! -d "$ROOT/vendor/DiffRhythm" ]; then
    git clone https://github.com/ASLP-lab/DiffRhythm.git vendor/DiffRhythm
    pip install -e vendor/DiffRhythm
    echo "  DiffRhythm installed."
else
    echo "  DiffRhythm already present."
fi

echo ""
echo "✅  Bootstrap complete. Next steps:"
echo "   mkdir build && cd build"
echo "   cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release -DWANT_QT6=ON"
echo "   ninja"
