from lark.indenter import PythonIndenter
from lark import Lark

test_code = """
func:
        return a + b

func(1, 2)
"""

grammar = open("python.lark", "r").read()
parser = Lark(grammar, start="file_input", postlex=PythonIndenter())

print(parser.parse(test_code).pretty())