from z3 import *
from compiler.element.node import Identifier, Literal, Expr, Operator, Pair, Program, Assign, Send

class SymbolicEnv:
    def __init__(self, state_vars):
        self.state = {name: Int(f"{name}0") for name in state_vars}
        self.send_log = []

    def eval_expr(self, expr):
        if isinstance(expr, Literal):
            if expr.value.isdigit():
                return IntVal(int(expr.value))
            return StringVal(expr.value)
        elif isinstance(expr, Identifier):
            return self.state[expr.name]
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
        elif isinstance(expr, Pair):
            return (self.eval_expr(expr.left), self.eval_expr(expr.right))
        raise NotImplementedError(f"Unknown expr: {expr}")

    def exec_stmt(self, stmt):
        stmt = stmt.stmt
        if isinstance(stmt, Assign):
            var = stmt.left.name
            val = self.eval_expr(stmt.right)
            self.state[var] = val
        elif isinstance(stmt, Send):
            pass
            # payload = self.eval_expr(stmt.msg)
            # self.send_log.append(payload)

    def exec_body(self, body):
        for stmt in body:
            self.exec_stmt(stmt)
    
    def bind_inputs(self, params, values):
        for p in params:
            self.inputs = values  

def check_idempotent(program: Program):
    state_vars = [s[0].name for s in program.definition.state]
    body = program.req.body

    # First execution
    env1 = SymbolicEnv(state_vars)
    env1.exec_body(body)

    # Second execution (same input/state)
    env2 = SymbolicEnv(state_vars)
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
    state_vars = [s[0].name for s in program.definition.state]
    params = [p.name for p in program.req.params]
    body = program.req.body

    # Step 2: Define two symbolic messages with different symbolic values
    m1 = {p: Int(f"{p}1") for p in params}
    m2 = {p: Int(f"{p}2") for p in params}

    # Step 3: Run m1 followed by m2
    env1 = SymbolicEnv(state_vars)
    env1.bind_inputs(params, m1)
    env1.exec_body(body)
    env1.bind_inputs(params, m2)
    env1.exec_body(body)
    state1 = env1.state.copy()

    # Step 4: Run m2 followed by m1
    env2 = SymbolicEnv(state_vars)
    env2.bind_inputs(params, m2)
    env2.exec_body(body)
    env2.bind_inputs(params, m1)
    env2.exec_body(body)
    state2 = env2.state.copy()

    # Step 5: Compare final symbolic state — ignore outputs for now
    solver = Solver()
    state_diff = Or([state1[k] != state2[k] for k in state1])
    solver.add(state_diff)
    
    print(state1)
    print(state2)

    if solver.check() == sat:
        print("❌ Ordering-sensitive (based on state):", solver.model())
    else:
        print("✅ Ordering-insensitive (based on state only)")