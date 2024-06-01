import os
import pathlib

from lark import Lark
from lark.indenter import Indenter


class AppNetIndenter(Indenter):
    NL_type = "_NEWLINE"
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    tab_len = 4


class ElementParser:
    def __init__(self):
        cwd = pathlib.Path(__file__).parent
        grammar = open(os.path.join(cwd, "python_style_grammar.lark"), "r").read()
        # grammar = open(os.path.join(cwd, "new.lark"), "r").read()
        self.lark_parser = Lark(grammar, start="appnet", postlex=AppNetIndenter())

    def parse(self, spec):
        return self.lark_parser.parse(spec)
