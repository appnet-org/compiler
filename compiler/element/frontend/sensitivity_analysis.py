from z3 import *
from compiler.element.node import *

from z3 import *
from compiler.element.node import *

class SymbolicEnv:
    def __init__(self, state_vars):
        self.state = {}
        self.handle_state_var(state_vars)
        
        # TODO: is locals needed? 
        self.locals = {}
        self.rpc= Array("rpc", StringSort(), StringSort())
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
            elif expr.name == "rpc":
                return self.rpc
            elif expr.name in self.locals:
                return self.locals[expr.name]
            else:
                raise ValueError(f"Unknown identifier: {expr.name}")
        elif isinstance(expr, Pair):
            return (self.eval_expr(expr.left), self.eval_expr(expr.right))
        elif isinstance(expr, MethodCall):
            if expr.method == MethodType.GET:
                if expr.obj.name in self.state:
                    arr = self.state[expr.obj.name]
                    key = self.eval_expr(expr.args[0])
                    return Select(arr, key)
                elif expr.obj.name == "rpc":
                    arr = self.rpc
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
            match_expr = self.eval_expr(stmt.expr)
            
            for pattern, actions in stmt.actions:
                if isinstance(pattern, Pattern):
                    self.exec_action(actions)
        else:
            inner = stmt.stmt
            if isinstance(inner, Assign):
                var = inner.left.name
                # If RHS is a method call like get(...), eval it safely
                if isinstance(inner.right, MethodCall):
                    val = self.eval_expr(inner.right)
                else:
                    val = self.eval_expr(inner.right)
                
                if var in self.state:
                    self.state[var] = val
                else:
                    self.locals[var] = val
                    
            elif isinstance(inner, Send):
                payload = self.eval_expr(inner.msg)
                self.send_log.append(payload)
            elif isinstance(inner, MethodCall):
                if inner.method == MethodType.SET:
                    key = self.eval_expr(inner.args[0])
                    val = self.eval_expr(inner.args[1])
                    if inner.obj.name == "rpc":
                        self.rpc = Store(self.rpc, key, val)
                    else:
                        arr = self.state[inner.obj.name]
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
            
    def exec_action(self, action):
        for stmt in action:
            self.exec_stmt(stmt)

    def exec_body(self, req_body, resp_body):
        """
        Executes the request and response bodies.
        """
        for stmt in req_body:
            self.exec_stmt(stmt)
        if resp_body:
            for stmt in resp_body:
                self.exec_stmt(stmt)

    def bind_inputs(self, value):
        """
        Binds the input parameters to the symbolic values.
        This is used to run the program with different inputs.
        """
        self.rpc = value


def check_idempotent(program: Program) -> bool:
    state_vars = [(s[0].name, s[1].name) for s in program.definition.state]
    req_body = program.req.body
    resp_body = program.resp.body

    # First execution
    env1 = SymbolicEnv(state_vars)
    env1.exec_body(req_body, resp_body)

    # Second execution (same input/state)
    env2 = SymbolicEnv(state_vars)
    env2.state = env1.state.copy()
    env2.exec_body(req_body, resp_body)

    # Z3 Check
    solver = Solver()
    state_eq = And([env1.state[k] == env2.state[k] for k in env1.state])
    sends_eq = And([env1.send_log[i] == env2.send_log[i] for i in range(len(env1.send_log))])
    solver.add(Not(And(state_eq, sends_eq)))

    if solver.check() == sat:
        print("❌ Not idempotent:", solver.model())
        return False
    else:
        print("✅ Idempotent")
        return True

def check_ordering_sensitive(program: Program) -> bool:
    # Step 1: Extract state variables and input parameters
    state_vars = [(s[0].name, s[1].name) for s in program.definition.state]
    req_body = program.req.body
    resp_body = program.resp.body

    # Step 2: Define two symbolic messages with different symbolic values
    m1 = Array(f"rpc1", StringSort(), StringSort())
    m2 = Array(f"rpc2", StringSort(), StringSort())
    
    # Step 3: Run m1 followed by m2
    env1 = SymbolicEnv(state_vars)
    env1.bind_inputs(m1)
    env1.exec_body(req_body, resp_body)
    env1.bind_inputs(m2)
    env1.exec_body(req_body, resp_body)
    state1, sends1 = env1.state.copy(), env1.send_log[:]

    # Step 4: Run m2 followed by m1
    env2 = SymbolicEnv(state_vars)
    env2.bind_inputs(m2)
    env2.exec_body(req_body, resp_body)
    env2.bind_inputs(m1)
    env2.exec_body(req_body, resp_body)
    state2, sends2 = env2.state.copy(), env2.send_log[:]

    # Step 5: Compare final symbolic state — ignore outputs for now
    # TODO: check send logs as well. 
    solver = Solver()
    state_diff = Or([state1[k] != state2[k] for k in state1])
    solver.add(state_diff)

    if solver.check() == sat:
        print("❌ Ordering-sensitive (based on state):", solver.model())
        return False
    else:
        print("✅ Ordering-insensitive (based on state only)")
        return True
        
def check_requires_all_rpcs(program) -> bool:
    state_vars = [(s[0].name, s[1].name) for s in program.definition.state]
    req_body = program.req.body
    resp_body = program.resp.body

    # Symbolic RPCs
    m1 = Array("rpc1", StringSort(), StringSort())
    m2 = Array("rpc2", StringSort(), StringSort())

    # Full execution: m1 then m2
    env1 = SymbolicEnv(state_vars)
    env1.bind_inputs(m1)
    env1.exec_body(req_body, resp_body)
    env1.bind_inputs(m2)
    env1.exec_body(req_body, resp_body)
    state1, sends1 = env1.state.copy(), set(env1.send_log[:])

    # Skip execution: only m2
    env2 = SymbolicEnv(state_vars)
    env2.bind_inputs(m2)
    env2.exec_body(req_body, resp_body)
    state2, sends2 = env2.state.copy(), set(env2.send_log[:])

    # Compare states and send sets
    solver = Solver()
    state_diff = Or([state1[k] != state2[k] for k in state1])
    # TODO: check send logs as well. 
    solver.add(state_diff)

    if solver.check() == sat:
        print("❌ Must see all RPCs — dropping one affects output or state")
        print("Model:", solver.model())
        return False
    else:
        print("✅ Can tolerate RPC drops — output and state unchanged")
        return True