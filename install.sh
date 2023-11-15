#!/bin/bash

set -e

# install python dependencies
sudo apt install -y python3-pip
pip install lark pre-commit tomli tomli_w colorlog


# Set up env variable
export PHOENIX_DIR="$HOME/phoenix"

set +e