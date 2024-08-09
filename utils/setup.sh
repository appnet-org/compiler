wget https://repo.anaconda.com/miniconda/Miniconda3-py310_23.3.1-0-Linux-x86_64.sh -O Miniconda.sh
bash Miniconda.sh

conda create -y -n appnet python=3.10
conda activate appnet

pip3 install tomli lark colorlog tomli_w