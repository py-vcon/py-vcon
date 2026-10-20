#!/bin/bash
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Build all three python-vcon packages in order from lowest to highest tier.
set -e

# Restore setup.py if script is interrupted
trap 'if [ -f setup_full.py ]; then mv setup_full.py setup.py; fi' EXIT

echo "Cleaning dist and egg directories..."
rm -rf dist python_vcon.egg-info python_vcon_core.egg-info python_vcon_light.egg-info

echo "Building python-vcon-core..."
mv setup.py setup_full.py
cp setup_core.py setup.py
python3 setup_core.py sdist bdist_wheel
mv setup_full.py setup.py

echo "Building python-vcon-light..."
mv setup.py setup_full.py
cp setup_light.py setup.py
python3 setup_light.py sdist bdist_wheel
mv setup_full.py setup.py

echo "Building python-vcon (full)..."
python3 -m build

echo "Build complete. Packages in dist/:"
ls dist/

