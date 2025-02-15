# AppNet Compiler

## Overview

This compiler is designed for translating AppNet specifications into optimized, deployable data plane programs. For more information, refer to our [HotNets paper](https://xzhu27.me/papers/adn-hotnets2023.pdf) and the [talk](https://www.youtube.com/watch?v=hJobLIq1Bmk).

## Preliminaries

We recommend using conda to configure the environment. Run the following commands to install Python 3.10 and relevant python library dependencies.

```bash
conda create -n appnet python=3.10
pip install -r requirements.txt
```

We assume that `compiler` is placed inside the [`appnet`](https://github.com/appnet-org/appnet) repository. Run the following scripts to install Kubernetes cluster and Istio.

```bash
# Install Kubernetes
. ../utils/k8s_setup.sh          # for control plane
. ../utils/k8s_setup_worker.sh   # for worker nodes

# Run the following command on the control plane node to get the join command, and run the join command on all worker nodes.
kubeadm token create --print-join-command

# Install Istio
. ../utils/istio_setup_ambient.sh
```

If you want to compile elements as gRPC interceptors, install Go and protobuf compiler dependencies.

```bash
# Install protobuf compiler
sudo apt install -y protobuf-compiler

# Install Go
wget https://go.dev/dl/go1.22.1.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.22.1.linux-amd64.tar.gz && sudo rm go1.22.1.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Install goimports
go install golang.org/x/tools/cmd/goimports@latest
echo 'export PATH=$PATH:/$HOME/go/bin' >> ~/.bashrc
source ~/.bashrc
```

If you want to compile elements as Envoy WASM filters, install the following Rust dependencies.

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"
rustup target add wasm32-wasip1
```


> [!Note]
>
> AppNet uses Docker Hub to distribute compiled Envoy native filters for simplicity, and currently the Hub name is hard-coded in configs and source code. If you want to compile elements as Envoy native filters, there are several modifications you need to apply during installation.
> * Register your own Docker Hub account.
> * In `istio_setup_ambient.sh` ([appnet](https://github.com/appnet-org/appnet) repository), replace the `hub=docker.io/appnetorg` argument of `istioctl install` with your own Hub ID.
> * In `compiler/graph/backend/imagehub.py`, replace `HUB_NAME="docker.io/appentorg` with your own Hub ID.

## Usage

A minimal example to run is

```bash
# Under compiler/

sed -i 's|<COMPILER_DIR>|'"$(pwd)"'|g' examples/chain/echo.yaml                       # replace all <COMPILER_DIR> with the path to compiler root directory
sed -i 's|<APPNET_GO_LIB_DIR>|'"$(realpath ../go-lib)"'|g' examples/chain/echo.yaml   # replace all <APPNET_GO_LIB_DIR> placeholder with the path to go-lib
python3 compiler/main.py --spec examples/chain/echo.yaml --opt_level weak
```

Use `--help` to see all avaiable options.

## Supported Backends

- [**Envoy**](https://www.envoyproxy.io/)
  - native
  - via [**Proxy WASM Rust SDK**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk)
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))

## Reference
Please consider citing our paper if you find AppNet related to your research.
```bibtex
@inproceedings{applicationdefinednetworks,
  title={Application Defined Networks},
  author={Zhu, Xiangfeng and Deng, Weixin and Liu, Banruo and Chen, Jingrong and Wu, Yongji and Anderson, Thomas and Krishnamurthy, Arvind and Mahajan, Ratul and Zhuo, Danyang},
  booktitle={Proceedings of the 22nd ACM Workshop on Hot Topics in Networks},
  pages={87--94},
  year={2023}
}
```

## Contact

If you have any questions or comments, please get in touch with Xiangfeng Zhu (xfzhu@cs.washington.edu).
