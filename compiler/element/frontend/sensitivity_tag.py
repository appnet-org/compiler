from z3 import *
from compiler.element.node import *

from z3 import *
from compiler.element.node import *

class SymbolicEnv:
    def __init__(self, state_vars, params):
        self.state = {}
        self.handle_state_var(state_vars)
        
        # TODO: params should just be rpc. 
        self.params = {name: Array(f"{name}0", StringSort(), StringSort()) for name in params}
        self.send_log = []

    def handle_state_var(self, state_vars):
        # TODO: handle other types of state variables
        for name, type in state_vars:
            if type.startswith("Map<"):
                self.state[name] = Array(f"{name}0", StringSort(), StringSort())
            else:
                self.state[name] = Int(f"{name}0")

    def eval_expr(self, expr):
        if isinstance(expr, Literal):
            if isinstance(expr.value, str) and expr.value.isdigit():
                return IntVal(int(expr.value))
            return StringVal(expr.value)
        elif isinstance(expr, Identifier):
            if expr.name in self.state:
                return self.state[expr.name]
            elif expr.name in self.params:
                return self.params[expr.name]
            else:
                raise ValueError(f"Unknown identifier: {expr.name}")
        elif isinstance(expr, Pair):
            return (self.eval_expr(expr.left), self.eval_expr(expr.right))
        elif isinstance(expr, MethodCall):
            if expr.method == MethodType.GET:
                if expr.obj.name in self.state:
                    arr = self.state[expr.obj.name]
                    print(arr)
                    key = self.eval_expr(expr.args[0])
                    return Select(arr, key)
                elif expr.obj.name in self.params:
                    arr = self.params[expr.obj.name]
                    key = self.eval_expr(expr.args[0])
                    return Select(arr, key)
                else:
                    raise ValueError(f"Unknown identifier: {expr.obj.name}")
            elif expr.method == MethodType.SET:
                # Should only be used in statement context
                raise RuntimeError("SET should not be evaluated as expression")
            elif expr.method == MethodType.DELETE:
                # Should only be used in statement context
                raise RuntimeError("DELETE should not be evaluated as expression")
        elif isinstance(expr, Expr):
            lhs = self.eval_expr(expr.lhs)
            rhs = self.eval_expr(expr.rhs)
            if expr.op == Operator.ADD:
                return lhs + rhs
            elif expr.op == Operator.SUB:
                return lhs - rhs
            elif expr.op == Operator.MUL:
                return lhs * rhs
            elif expr.op == Operator.DIV:
                return lhs / rhs
            elif expr.op == Operator.EQ:
                return lhs == rhs
            elif expr.op == Operator.NEQ:
                return lhs != rhs
            elif expr.op == Operator.LT:
                return lhs < rhs
            elif expr.op == Operator.GT:
                return lhs > rhs
            elif expr.op == Operator.LE:
                return lhs <= rhs
            elif expr.op == Operator.GE:
                return lhs >= rhs
            else:
                raise NotImplementedError(f"Unsupported operator: {expr.op}")

        else:
            raise NotImplementedError(f"Unknown expr: {expr}")

    def exec_stmt(self, stmt):
        if isinstance(stmt, Match):
            # TODO: add full match handling
            pass
        else:
            inner = stmt.stmt
            if isinstance(inner, Assign):
                var = inner.left.name
                # If RHS is a method call like get(...), eval it safely
                if isinstance(inner.right, MethodCall):
                    val = self.eval_expr(inner.right)
                else:
                    val = self.eval_expr(inner.right)
                self.state[var] = val
            elif isinstance(inner, Send):
                payload = self.eval_expr(inner.msg)
                self.send_log.append(payload)
            elif isinstance(inner, MethodCall):
                if inner.method == MethodType.SET:
                    arr = self.state[inner.obj.name]
                    key = self.eval_expr(inner.args[0])
                    val = self.eval_expr(inner.args[1])
                    self.state[inner.obj.name] = Store(arr, key, val)
                elif inner.method == MethodType.DELETE:
                    arr = self.state[inner.obj.name]
                    key = self.eval_expr(inner.args[0])
                    self.state[inner.obj.name] = Store(arr, key, StringVal("None"))
                elif inner.method == MethodType.GET:
                    # No effect as a statement
                    _ = self.eval_expr(inner)
                else:
                    raise NotImplementedError(f"Unsupported method call type in stmt: {inner.method}")
            else:
                raise NotImplementedError(f"Unknown statement type: {type(inner)}")

    def exec_body(self, body):
        for stmt in body:
            self.exec_stmt(stmt)

    def bind_inputs(self, params, values):
        for p in params:
            self.params[p] = values[p]


def check_idempotent(program: Program):
    state_vars = [(s[0].name, s[1].name) for s in program.definition.state]
    params = [p.name for p in program.req.params]
    body = program.req.body

    # First execution
    env1 = SymbolicEnv(state_vars, params)
    env1.exec_body(body)

    # Second execution (same input/state)
    env2 = SymbolicEnv(state_vars, params)
    env2.state = env1.state.copy()
    env2.exec_body(body)

    # Z3 Check
    solver = Solver()
    state_eq = And([env1.state[k] == env2.state[k] for k in env1.state])
    sends_eq = And([env1.send_log[i] == env2.send_log[i] for i in range(len(env1.send_log))])
    solver.add(Not(And(state_eq, sends_eq)))

    if solver.check() == sat:
        print("❌ Not idempotent:", solver.model())
    else:
        print("✅ Idempotent")

def check_ordering_sensitive(program: Program):
    # Step 1: Extract state variables and input parameters
    state_vars = [(s[0].name, s[1].name) for s in program.definition.state]
    params = [p.name for p in program.req.params]
    body = program.req.body

    # Step 2: Define two symbolic messages with different symbolic values
    m1 = {p: Int(f"{p}1") for p in params}
    m2 = {p: Int(f"{p}2") for p in params}

    # Step 3: Run m1 followed by m2
    env1 = SymbolicEnv(state_vars, params)
    env1.bind_inputs(params, m1)
    env1.exec_body(body)
    env1.bind_inputs(params, m2)
    env1.exec_body(body)
    state1, sends1 = env1.state.copy(), env1.send_log[:]
    # print(sends1)

    # Step 4: Run m2 followed by m1
    env2 = SymbolicEnv(state_vars, params)
    env2.bind_inputs(params, m2)
    env2.exec_body(body)
    env2.bind_inputs(params, m1)
    env2.exec_body(body)
    state2, sends2 = env2.state.copy(), env2.send_log[:]
    # print(sends2)

    # Step 5: Compare final symbolic state — ignore outputs for now
    solver = Solver()
    state_diff = Or([state1[k] != state2[k] for k in state1])
    solver.add(state_diff)

    if solver.check() == sat:
        print("❌ Ordering-sensitive (based on state):", solver.model())
    else:
        print("✅ Ordering-insensitive (based on state only)")