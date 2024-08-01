#!/bin/bash

# operate on CloudLab Image u2004

git clone git@github.com:appnet-org/appnet.git --recursive
cd appnet

. ./utils/k8s_setup.sh

wget https://go.dev/dl/go1.22.1.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.22.1.linux-amd64.tar.gz

echo "export PATH=$PATH:/usr/local/go/bin" >> ~/.bashrc
source ~/.bashrc

sudo apt -y install protobuf-compiler


wget https://repo.anaconda.com/miniconda/Miniconda3-py310_23.3.1-0-Linux-x86_64.sh -O Miniconda.sh
bash Miniconda.sh


pip3 install pyyaml rich

