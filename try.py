from lark import Lark
from lark.indenter import Indenter

tree_grammar = r"""
    start: _NEWLINE* definition _NEWLINE*

    definition: "state" ":" _NEWLINE _INDENT declaration* _DEDENT

    declaration: (consistency_decorator | combiner_decorator | persistence_decorator)* identifier ":" type_ _NEWLINE
    consistency_decorator: "@consistency" "(" NAME ")"
    combiner_decorator: "@combiner" "(" NAME ")"
    persistence_decorator: "@persistence" "(" bool ")"

    bool: "true" -> true | "false" -> false

    identifier: NAME

    type_: single_type
        | "Vec" "<" single_type ">"  -> vec_type
        | "Map" "<" single_type "," single_type ">" -> map_type

    single_type: NAME

    _NEWLINE: ( /\r?\n[\t ]*/ | COMMENT )+
    COMMENT: /#[^\n]*/
    NAME: /[^\W\d]\w*/
    %ignore /[\t \f]+/  // WS
    %ignore /\\[\t \f]*\r?\n/   // LINE_CONT
    %ignore COMMENT
    %declare _INDENT _DEDENT
"""

class TreeIndenter(Indenter):
    NL_type = '_NEWLINE'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4

parser = Lark(tree_grammar, start="start", postlex=TreeIndenter())

test_tree = """
state:
    acl: Map<string, string>
"""

def test():
    print(parser.parse(test_tree).pretty())

if __name__ == '__main__':
    test()