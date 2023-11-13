#!/bin/bash

set -e

# install python dependencies
pip install lark pre-commit tomli tomli_w colorlog

COMPILER_DIR="$(dirname $(readlink -f "$0"))/compiler"
ROOT_DIR=$(dirname $COMPILER_DIR)
export PYTHONPATH=$PYTHONPATH:$COMPILER_DIR:$ROOT_DIR
export PHOENIX_DIR="$HOME/phoenix"


set +e