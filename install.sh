#!/bin/bash

set -e  # Exit on error
SCRIPT_DIR=$(dirname "$(realpath "$0")")  # Get the directory of the script

echo "Updating package list..."
# sudo apt update
apt update

# Check if Open Babel is already installed
if command obabel -V &> /dev/null; then
    echo "Open Babel is already installed. Skipping installation."
else
    echo "Installing required system dependencies..."
    apt install -y cmake g++ libeigen3-dev libboost-all-dev libxml2-dev libz-dev swig python3-dev python3-pip git

    echo "Installing Open Babel..."
    git clone https://github.com/openbabel/openbabel.git
    cd openbabel
    mkdir build && cd build
    cmake .. -DPYTHON_BINDINGS=ON -DPYTHON_EXECUTABLE=$(which python3) -DRUN_SWIG=ON
    make -j$(nproc)
    make install  # Ensure system-wide installation

    cd "$SCRIPT_DIR"

    echo "Setting up Open Babel environment..."
    echo "/usr/local/lib" | tee -a /etc/ld.so.conf.d/openbabel.conf
    ldconfig
    echo 'export LD_LIBRARY_PATH="/usr/local/lib:$LD_LIBRARY_PATH"' >> ~/.bashrc
    source ~/.bashrc
    ldconfig

    echo "Verifying Open Babel installation..."
    obabel -H || { echo "Open Babel installation failed"; exit 1; }
fi

cd "$SCRIPT_DIR"

echo "Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "Setting up Open Babel environment..."
echo "/usr/local/lib" | tee -a /etc/ld.so.conf.d/openbabel.conf
ldconfig
echo 'export LD_LIBRARY_PATH="/usr/local/lib:$LD_LIBRARY_PATH"' >> ~/.bashrc
source ~/.bashrc

echo "Installation complete!"
