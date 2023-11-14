#!/bin/bash

set -e

# install python dependencies
sudo apt install -y python3-pip
pip install lark pre-commit tomli tomli_w colorlog


# Set up env variable
echo "export ADN_COMPILER_DIR=$PWD" >> ~/.bashrc
echo "export PYTHONPATH=$PYTHONPATH:$ADN_COMPILER_DIR:$ADN_COMPILER_DIR/compiler" >> ~/.bashrc
echo "export PHOENIX_DIR="$HOME/phoenix"" >> ~/.bashrc
. ~/.bashrc

set +e