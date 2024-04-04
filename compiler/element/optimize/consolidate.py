from copy import deepcopy
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.node import Expr, Identifier, State, MethodCall, Procedure
from compiler.element.visitor import Visitor


def consolidate(irs: List[Program]) -> Program:
    while len(irs) > 1:
        left = irs.pop(0)
        right = irs.pop(0)
        new_prog = Program(
            State([]),
            Procedure("init", [], []),
            Procedure("req", [], []),
            Procedure("resp", [], []),
        )

        new_prog.definition.state = deepcopy(
            left.definition.state + right.definition.state
        )

        InitConsolidator().visitProcedure(new_prog.init, (left.init, right.init))
        ProcedureConsolidator().visitProcedure(
            new_prog.req, (deepcopy(left.req), deepcopy(right.req))
        )
        ProcedureConsolidator().visitProcedure(
            new_prog.resp, (deepcopy(right.resp), deepcopy(left.resp))
        )

        irs.insert(0, new_prog)
    return irs[0]


class InitConsolidator(Visitor):
    def __init__(self):
        pass

    def visitNode(self, node: Node, ctx) -> str:
        LOG.error("InitConsolidator: visitNode not implemented")
        raise NotImplementedError

    def visitProcedure(
        self, node: Procedure, ctx: Tuple[Procedure, Procedure]
    ) -> Procedure:
        l, r = ctx
        node.name = "init"
        node.params = deepcopy(list(set(l.params + r.params)))
        node.body = deepcopy(l.body + r.body)


class ProcedureConsolidator(Visitor):
    def __init__(self):
        pass

    def visitNode(self, node: Node, ctx) -> str:
        LOG.error("ReqConsolidator: visitNode not implemented")
        raise NotImplementedError

    def visitProcedure(
        self, node: Procedure, ctx: Tuple[Procedure, Procedure]
    ) -> Procedure:
        l, r = ctx
        assert l.name == r.name
        node.params = deepcopy(list(set(l.params + r.params)))
        node.body = []
        for s in l.body:
            if isinstance(s, Match):
                ret = s.accept(self, r.body)
                node.body.append(deepcopy(ret))
            elif isinstance(s, Assign):
                node.body.append(deepcopy(s))
            elif isinstance(s, Send):
                is_send = s.accept(self, r.body)
                if is_send:
                    node.body += deepcopy(r.body)
                else:
                    node.body.append(deepcopy(s))
            elif isinstance(s.stmt, Send):
                is_send = s.stmt.accept(self, r.body)
                if is_send:
                    node.body += deepcopy(r.body)
                else:
                    node.body.append(deepcopy(s))
            else:
                LOG.warning(f"Unexpected statement {s}")
                node.body.append(deepcopy(s))

    def visitMatch(self, node: Match, ctx: List[Statement]):
        match = Match(deepcopy(node.expr), [])
        for (p, s) in node.actions:
            rs = []
            for st in s:
                if isinstance(st, Match):
                    ret = st.accept(self, ctx)
                    rs.append(deepcopy(ret))
                elif isinstance(st, Assign):
                    rs.append(deepcopy(st))
                elif isinstance(st, Send):
                    is_send = st.accept(self, ctx)
                    if is_send:
                        rs = rs + deepcopy(ctx)
                    else:
                        rs.append(deepcopy(st))
                elif isinstance(st.stmt, Send):
                    is_send = st.stmt.accept(self, ctx)
                    if is_send:
                        rs = rs + deepcopy(ctx)
                    else:
                        rs.append(deepcopy(st))
                else:
                    LOG.warning(f"Unexpected statement {st}")
                    rs.append(deepcopy(st))
            match.actions.append((deepcopy(p), rs))
        return match

    def visitSend(self, node: Send, ctx) -> bool:
        if isinstance(node.msg, Error):
            return False
        else:
            return True
