# Compiler for Application Defined Networks

# Overview

This compiler is designed for translating ADN specifications into optimized, deployable data plane programs. For more information, refer to our [HotNets paper](https://xzhu27.me/papers/adn-hotnets2023.pdf) and the [talk](https://www.youtube.com/watch?v=hJobLIq1Bmk).

# Installation
## Requirements
- Python (Version >= 3.10)

Please make sure that you clone the adn-compiler repository under `$HOME`.
```bash
git clone https://github.com/adn-compiler ~/adn-compiler
```

Run the following script to install necessary tools:
```bash
cd ~/adn-compiler
. ./install.sh
```

# Usage
See [compiler README ](./compiler/README.md) for usage.


## Supported Backends

- [**mRPC**](https://github.com/phoenix-dataplane/phoenix) 
- [**Envoy**](https://www.envoyproxy.io/) (via [**Proxy WASM**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk))
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))
    - In progress

# Repo Structure
```
Repo Root
|---- examples   
|---- compiler  # Compiler source code
  |---- docs    # Miscellaneous docs
  |---- element # Source code for ADN graph compiler
  |---- graph   # Source code for ADN element compiler
```

# Reference
Please consider citing our paper if you find MeshInsight related to your research.
```bibtex
@inproceedings{applicationdefinednetworks,
  title={Application Defined Networks},
  author={Zhu, Xiangfeng and Deng, Weixin and Liu, Banruo and Chen, Jingrong and Wu, Yongji and Anderson, Thomas and Krishnamurthy, Arvind and Mahajan, Ratul and Zhuo, Danyang},
  booktitle={Proceedings of the 22nd ACM Workshop on Hot Topics in Networks},
  pages={87--94},
  year={2023}
}
```


# Contact

If you have any questions or comments, please get in touch with Xiangfeng Zhu (xfzhu@cs.washington.edu).