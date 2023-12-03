# Element Compiler

Element compiler convert match-action code to IR. From IR, we can infer the property (read/written, drop) for each NF and provide graph compiler with the information. Element compiler also generates backend code(mRPC) for each NF.

## usage

```
cd compiler
export PYTHONPATH=$PYTHONPATH:$(pwd):$(dirname $(pwd))
python ir_main.py -e acl -v True
# v for verbose, which is `false` by default
# refer to example/match-action for more engine names
```
