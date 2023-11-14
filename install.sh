#!/bin/bash

set -e

# install python dependencies
sudo apt install -y python3-pip
pip install lark pre-commit tomli tomli_w colorlog


# Set up env variable
SHELL_NAME=$(ps -o fname --no-headers $$)
if [ $SHELL_NAME = 'bash' ]
then
    ADN_COMPILER_DIR=$(dirname $(realpath $BASH_SOURCE))
else
    ADN_COMPILER_DIR=$(dirname $(realpath $0))
fi
export PYTHONPATH=$PYTHONPATH:$ADN_COMPILER_DIR:$ADN_COMPILER_DIR/compiler
export PHOENIX_DIR="$HOME/phoenix"

set +e