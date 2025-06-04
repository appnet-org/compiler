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
            # Handle other operators...
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
            payload = self.eval_expr(stmt.msg)
            self.send_log.append(payload)

    def exec_body(self, body):
        for stmt in body:
            self.exec_stmt(stmt)

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
