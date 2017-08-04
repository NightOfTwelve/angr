import logging

import ailment
import pyvex

from ..engine import SimEngine
from ..vex.irop import operations as vex_operations
from ...analyses.code_location import CodeLocation

l = logging.getLogger("angr.engines.light.engine")


class SimEngineLight(SimEngine):

    def __init__(self, engine_type='vex'):
        super(SimEngineLight, self).__init__()

        self.engine_type = engine_type

        # local variables
        self.state = None
        self.arch = None
        self.block = None

        self.stmt_idx = None
        self.ins_addr = None
        self.tmps = None

    def process(self, state, *args, **kwargs):
        # we are using a completely different state. Therefore, we directly call our _process() method before
        # SimEngine becomes flexible enough.
        self._process(state, None, block=kwargs.pop('block', None))


class SimEngineLightVEX(SimEngineLight):

    def __init__(self):
        super(SimEngineLightVEX, self).__init__()

        # for VEX blocks only
        self.tyenv = None

    def _process(self, state, successors, block=None):

        assert block is not None

        # initialize local variables
        self.tmps = { }
        self.block = block
        self.state = state
        self.arch = state.arch

        self.tyenv = block.vex.tyenv

        self._process_Stmt()

        self.stmt_idx = None
        self.ins_addr = None

    def _process_Stmt(self):

        for stmt_idx, stmt in enumerate(self.block.vex.statements):
            self.stmt_idx = stmt_idx

            if type(stmt) is pyvex.IRStmt.IMark:
                self.ins_addr = stmt.addr + stmt.delta

            self._handle_Stmt(stmt)

    #
    # Helper methods
    #

    def _codeloc(self):
        return CodeLocation(self.block.addr, self.stmt_idx, ins_addr=self.ins_addr)

    #
    # Statement handlers
    #

    def _handle_Stmt(self, stmt):
        handler = "_handle_%s" % type(stmt).__name__
        if hasattr(self, handler):
            getattr(self, handler)(stmt)
        else:
            l.warning('Unsupported statement type %s.', type(stmt).__name__)

    def _handle_WrTmp(self, stmt):
        data = self._expr(stmt.data)
        if data is None:
            return

        self.tmps[stmt.tmp] = data

    def _handle_Put(self, stmt):
        raise NotImplementedError('Please implement the Put handler with your own logic.')

    def _handle_Store(self, stmt):
        raise NotImplementedError('Please implement the Store handler with your own logic.')

    #
    # Expression handlers
    #

    def _expr(self, expr):

        handler = "_handle_%s" % type(expr).__name__
        if hasattr(self, handler):
            return getattr(self, handler)(expr)
        else:
            l.warning('Unsupported expression type %s.', type(expr).__name__)
        return None

    def _handle_RdTmp(self, expr):
        tmp = expr.tmp

        if tmp in self.tmps:
            return self.tmps[tmp]
        return None

    def _handle_Get(self, expr):
        raise NotImplementedError('Please implement the Get handler with your own logic.')

    def _handle_Load(self, expr):
        raise NotImplementedError('Please implement the Load handler with your own logic.')

    def _handle_UnaryOp(self, expr):
        simop = vex_operations[expr.op]
        if simop._conversion:
            handler_name = '_handle_Conversion'
        else:
            handler_name = '_handle_%s' % expr.op

        try:
            handler = getattr(self, handler_name)
        except AttributeError:
            l.warning('Unsupported UnaryOp %s.', expr.op)
            return None

        return handler(expr)

    def _handle_Binop(self, expr):
        if expr.op.startswith('Iop_Add'):
            return self._handle_Add(*expr.args)
        elif expr.op.startswith('Iop_Sub'):
            return self._handle_Sub(*expr.args)
        elif expr.op.startswith('Const'):
            return self._handle_Const(*expr.args)

        return None

    #
    # Binary operation handlers
    #

    def _handle_Add(self, arg0, arg1):
        expr_0 = self._expr(arg0)
        if expr_0 is None:
            return None
        expr_1 = self._expr(arg1)
        if expr_1 is None:
            return None

        try:
            return expr_0 + expr_1
        except TypeError:
            return None

    def _handle_Sub(self, arg0, arg1):
        expr_0 = self._expr(arg0)
        if expr_0 is None:
            return None
        expr_1 = self._expr(arg1)
        if expr_1 is None:
            return None

        try:
            return expr_0 - expr_1
        except TypeError:
            return None

    def _handle_Const(self, arg):  #pylint:disable=no-self-use
        return arg.con.value


class SimEngineLightAIL(SimEngineLight):
    def __init__(self):
        super(SimEngineLightAIL, self).__init__(engine_type='ail')

    def _process(self, state, successors, block=None):

        self.tmps = { }
        self.block = block
        self.state = state
        self.arch = state.arch

        self._process_Stmt()

        self.stmt_idx = None
        self.ins_addr = None

    def _process_Stmt(self):

        for stmt_idx, stmt in enumerate(self.block.statements):
            self.stmt_idx = stmt_idx
            self.ins_addr = stmt.ins_addr

            self._ail_handle_Stmt(stmt)

    def _expr(self, expr):

        handler = "_ail_handle_%s" % type(expr).__name__
        if hasattr(self, handler):
            return getattr(self, handler)(expr)
        l.warning('Unsupported expression type %s.', type(expr).__name__)
        return None

    #
    # Helper methods
    #

    def _codeloc(self):
        return CodeLocation(self.block.addr, self.stmt_idx, ins_addr=self.ins_addr)

    #
    # Statement handlers
    #

    def _ail_handle_Stmt(self, stmt):
        handler = "_ail_handle_%s" % type(stmt).__name__
        if hasattr(self, handler):
            getattr(self, handler)(stmt)
        else:
            l.warning('Unsupported statement type %s.', type(stmt).__name__)

    def _ail_handle_Jump(self, stmt):
        raise NotImplementedError('Please implement the Jump handler with your own logic.')

    def _ail_handle_Call(self, stmt):
        raise NotImplementedError('Please implement the Call handler with your own logic.')

    #
    # Expression handlers
    #

    def _ail_handle_Const(self, expr):
        return expr.value

    def _ail_handle_Tmp(self, expr):
        tmp_idx = expr.tmp_idx

        try:
            return self.tmps[tmp_idx]
        except KeyError:
            return None

    def _ail_handle_Load(self, expr):
        raise NotImplementedError('Please implement the Load handler with your own logic.')

    def _ail_handle_UnaryOp(self, expr):
        handler_name = '_ail_handle_%s' % expr.op
        try:
            handler = getattr(self, handler_name)
        except AttributeError:
            l.warning('Unsupported UnaryOp %s.', expr.op)
            return None

        return handler(expr)

    def _ail_handle_BinaryOp(self, expr):
        handler_name = '_ail_handle_%s' % expr.op
        try:
            handler = getattr(self, handler_name)
        except AttributeError:
            l.warning('Unsupported BinaryOp %s.', expr.op)
            return None

        return handler(expr)

    #
    # Binary operation handlers
    #

    def _ail_handle_Add(self, expr):

        arg0, arg1 = expr.operands

        expr_0 = self._expr(arg0)
        expr_1 = self._expr(arg1)
        if expr_0 is None:
            expr_0 = arg0
        if expr_1 is None:
            expr_1 = arg1

        try:
            return expr_0 + expr_1
        except TypeError:
            return ailment.Expr.BinaryOp(expr.idx, 'Add', [ expr_0, expr_1 ], **expr.tags)

    def _ail_handle_Sub(self, expr):

        arg0, arg1 = expr.operands

        expr_0 = self._expr(arg0)
        expr_1 = self._expr(arg1)

        if expr_0 is None:
            expr_0 = arg0
        if expr_1 is None:
            expr_1 = arg1

        try:
            return expr_0 - expr_1
        except TypeError:
            return ailment.Expr.BinaryOp(expr.idx, 'Sub', [ expr_0, expr_1 ], **expr.tags)
