from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.node import Expr, Identifier, Internal, MethodCall, Procedure
from compiler.element.visitor import Visitor


def consolidate(irs: List[Program]) -> Program:
    while len(irs) > 1:
        left = irs.pop(0)
        right = irs.pop(0)
        new_prog = Program()
        new_prog.internal = left.internal + right.internal
        new_prog.init = InitConsolidator().visitProcedure(
            new_prog.init, (left.init, right.init)
        )
        new_prog.req = ProcedureConsolidator().visitProcedure(
            new_prog.req, (left.req, right.req)
        )
        new_prog.resp = ProcedureConsolidator().visitProcedure(
            new_prog.resp, (right.resp, left.resp)
        )
        irs.append(new_prog)

    return irs[0]


def InitConsolidator(Visitor):
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
        node.param = list(set(l.param + r.param))
        node.body = l.body + r.body
        return node


def ProcedureConsolidator(Visitor):
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
        node.name = l.name
        node.param = list(set(l.param + r.param))
        node.body = []
        for s in l.body:
            if isinstance(s, Match):
                ret = s.accept(self, r.body)
                node.body.append(ret)
            elif isinstance(s, Send):
                is_send = s.accept(self, r.body)
                if is_send:
                    node.body.append(r.body)
                else:
                    node.body.append(s)
            else:
                node.body.append(s)
        return node

    def visitStatement(self, node: Statement, ctx):
        LOG.error("ReqConsolidator: visitStatement not implemented")
        raise NotImplementedError

    def visitMatch(self, node: Match, ctx: List[Statement]):
        ret = Match()
        ret.match = node.match
        for (p, s) in node.actions:
            rs = []
            for st in s:
                if isinstance(st, Send):
                    is_send = st.accept(self, ctx)
                    if is_send:
                        rs = rs + ctx
                    else:
                        rs.append(st)
                elif isinstance(st, Match):
                    ret = st.accept(self, ctx)
                    rs.append(ret)
                else:
                    rs.append(st)
            ret.actions.append((p, rs))
        return ret

    def visitSend(self, node: Send, ctx) -> bool:
        if isinstance(node.msg, Error):
            return False
        else:
            return True
