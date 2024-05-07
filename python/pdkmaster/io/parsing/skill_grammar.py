"""
A modgrammar for Cadence SKILL files

Top Grammar is SkillFile.
This grammar wants to parse all valid SKILL scripts, including Cadence text technology files,
Assura rules etc. This parser may parse invalid SKILL scripts.
"""
# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0

import re
from collections import OrderedDict


__all__ = ["SkillFile"]


from modgrammar import (
    Grammar, L, NOT_FOLLOWED_BY, WORD, REF, OPTIONAL, WHITESPACE, ZERO_OR_MORE, ONE_OR_MORE,
)
from modgrammar.extras import RE

grammar_whitespace_mode = "explicit"
# Include comments in whitespace
grammar_whitespace = re.compile(r'(\s+|;.*?\n|/\*(.|\n)*?\*/)+')

# Override this value to True in user code to enable parser debug output.
_debug = False


#
# Script interpretation support class
#
class SkillContext:
    def __init__(self, *, parent=None):
        self.parent = parent
        self.variables = {}
        self.procedures = {}
        self.called = {}

    def get_root(self):
        root = self
        while root.parent is not None:
            root = root.parent
        return root

    def add_var(self, assign):
        """Add variable with initial value to current context"""
        assert isinstance(assign, dict) and len(assign) == 1
        self.variables.update(assign)

    def update_var(self, assign):
        """Update variable value

        If variable does not exist in the context tree it will be added to the top
        context."""
        assert isinstance(assign, dict) and len(assign) == 1
        name = next(iter(assign))
        context = self
        while (context.parent is not None) and (name not in context.variables):
            context = context.parent
        context.variables.update(assign)

    def get_var(self, name):
        """Get value of a variable name.

        This will search the whole context tree and return the corresponding value.
        If variable is not found the name will be returned"""
        if name in self.variables:
            return self.variables[name]
        elif self.parent is not None:
            return self.parent.get_var(name)
        else:
            return name

    def get_procedure(self, name):
        """Get the procedure with a certain name"""
        if name in self.procedures:
            return self.procedures[name]
        elif self.parent is not None:
            return self.parent.get_procedure(name)
        else:
            return None

    def add_procedures(self, procedures):
        double = set(self.procedures.keys()).intersection(set(procedures.keys()))
        if double:
            raise ValueError(f"procedures {double} already present")

        self.procedures.update(procedures)


class SkillInterpreter:
    def __init__(self):
        self.callbacks = {
            "setq": (self.interpret_setq, {}),
            "let": (self.interpret_let, {}),
        }

    def register_callback(self, name, func, *, force_register=False, **kwargs):
        if not isinstance(name, str):
            raise TypeError("name has to be a string")
        if (name in self.callbacks) and not force_register:
            raise ValueError(f"callback '{name}' already registered")
        if not callable(func):
            raise TypeError("func has to callable")

        self.callbacks[name] = (func, kwargs)

    def __call__(self, *, expr, context=None):
        if context is None:
            context = SkillContext()
        ret = None

        if isinstance(expr, list):
            if len(expr) == 0:
                ret = False
            elif len(expr) > 1 and expr[0] == "!":
                arg = self(expr = expr[1:], context=context)
                if isinstance(arg, bool):
                    ret = not arg
                else:
                    ret = ['!', arg]
            elif (len(expr) >= 3) and (expr[1] in ('=', "==", "<", "<=", ">", ">=")):
                op = expr[1]
                if op == '=':
                    subexpr = expr[2] if len(expr) == 3 else expr[2:]
                    func, kwargs = self.callbacks["setq"]
                    ret = func(context, [expr[0], subexpr], **kwargs)
                elif expr[1] in ("==", "<", "<=", ">", ">="):
                    left = self(expr=expr[0], context=context)
                    right = self(expr=expr[2:])
                    if (isinstance(left, (int, float))
                        and isinstance(right, (int, float))
                       ):
                        if op == "==":
                            ret = (left == right)
                        elif op == "<":
                            ret = (left < right)
                        elif op == "<=":
                            ret = (left <= right)
                        elif op == ">":
                            ret = (left > right)
                        elif op == ">=":
                            ret = (left >= right)
                        else:
                            raise AssertionError("Internal error")
                    else:
                        ret = [left, op, right]
                else:
                    raise AssertionError("Internal error")
            else:
                for subexpr in expr:
                    ret = self(expr=subexpr, context=context)

        elif isinstance(expr, dict):
            assert len(expr) == 1
            for key, body in expr.items():
                if key == "when":
                    key = "if"

                try:
                    func, kwargs = self.callbacks[key]
                except KeyError:
                    ret = f"FUNCCALL:{key}"
                else:
                    ret = func(context, body, **kwargs)

                called = context.get_root().called
                try:
                    called[key] += 1
                except KeyError:
                    called[key] = 1
        elif isinstance(expr, str):
            ret = context.get_var(expr)
        else:
            ret = expr
        
        return ret

    def interpret_setq(self, context, args):
        assert isinstance(args, list) and (len(args) == 2) and isinstance(args[0], str)
        ret = self(expr=args[1], context=context)
        context.update_var({args[0]: ret})

        return ret

    def interpret_let(self, context, args):
        subcontext = SkillContext(parent=context)
        for var in args["vars"]:
            initvalue = None
            if isinstance(var, list):
                assert(1 <= len(var) <= 2)
                if len(var) > 1:
                    initvalue = self(context, var[1])
            var = var[0]
            assert isinstance(var, str)
            subcontext.add_var({var: initvalue})
            
        return self(args["statements"], context=subcontext)


#
# SKILL builtin functions
#
def _skill_let(elems, **kwargs):
    return {
        "vars": elems[0],
        "statements": elems[1],
    }


def _skill_for(elems, **kwargs):
    assert len(elems) > 3
    return {
        "var": elems[0],
        "begin": elems[1],
        "end": elems[2],
        "statements": elems[3:],
    }


def _skill_foreach(elems, **kwargs):
    assert len(elems) > 2
    return {
        "var": elems[0],
        "list": elems[1],
        "statements": elems[2:],
    }


def _skill_if(elems, **kwargs):
    thenidx = None
    elseidx = None
    for i, item in enumerate(elems):
        if type(item) is str:
            if item == "then":
                thenidx = i
            if item == "else":
                elseidx = i
    cond = elems[0]
    while isinstance(cond, list) and len(cond) == 1:
        cond = cond[0]
    value = {"cond": cond}
    if thenidx is not None:
        assert thenidx == 1
        value["then"] = elems[thenidx+1:elseidx]
        if elseidx is not None:
            value["else"] = elems[elseidx+1:]
    else:
        assert elseidx is None
        assert 2 <= len(elems) <= 3
        value["then"] = elems[1]
        if len(elems) > 2:
            value["else"] = elems[2]

    return value


def _skill_when(elems, **kwargs):
    assert len(elems) > 1
    cond = elems[0]
    while isinstance(cond, list) and len(cond) == 1:
        cond = cond[0]

    return {
        "cond": cond,
        "then": elems[1:],
    }


def _skill_functionlist(elems, **kwargs):
    """A list of functions with value converted to a dict with the function names as keys"""
    
    value = {}
    for elem in elems:
        assert isinstance(elem, dict) and len(elem) == 1
        value.update(elem)

    return value


_builtins = {
    "let": _skill_let,
    "prog": _skill_let, # Dont make distinction in return() handling
    "for": _skill_for,
    "foreach": _skill_foreach,
    "if": _skill_if,
    "when": _skill_when,
}


#
# SKILL Grammar
#
class _BaseGrammar(Grammar):
    def __init__(self, *args):
        super().__init__(*args)
        if _debug:
            start = self._str_info[1]
            end = self._str_info[2]
            print(f"{self.__class__.__name__}: {start}-{end}")


class Symbol(_BaseGrammar):
    grammar = RE(r"'[a-zA-Z_][a-zA-Z0-9_]*")

    def grammar_elem_init(self, sessiondata):
        self.value = self.string[1:]
        self.ast = {"Symbol": self.value}


class Bool(_BaseGrammar):
    grammar = L("t")|L("nil"), NOT_FOLLOWED_BY(WORD("a-zA-Z0-9_"))

    def grammar_elem_init(self, sessiondata):
        self.value = self.string == "t"
        self.ast = {"Bool": self.value}


class Identifier(_BaseGrammar):
    grammar = WORD("a-zA-Z_?@", "a-zA-Z0-9_?@."), NOT_FOLLOWED_BY(L("("))

    def grammar_elem_init(self, sessiondata):
        self.ast = {"Identifier": self.string}
        self.value = self.string


class Number(_BaseGrammar):
    grammar = RE(r"(\+|\-)?([0-9]+(\.[0-9]*)?|\.[0-9]+)(e(\+|-)?[0-9]+)?")

    def grammar_elem_init(self, sessiondata):
        isfloat = ("." in self.string) or ("e" in self.string)
        self.value = float(self.string) if isfloat else int(self.string)
        self.ast = {"Number": self.value}


class String(_BaseGrammar):
    grammar = RE(r'"([^"\\]+|\\(.|\n))*"')

    def grammar_elem_init(self, sessiondata):
        self.value = self.string
        self.ast = {"String": self.value}


class SignSymbol(_BaseGrammar):
    # +/- followed by a digit
    grammar_whitespace_mode = "explicit"
    grammar = RE(r"[\+\-](?=[0-9])")


class SignOperator(_BaseGrammar):
    # +/- not followed by a digit
    grammar = RE(r"[\+\-](?![\+\-0-9])")


class PrefixOperator(_BaseGrammar):
    grammar = L("!") | RE(r"\+(?!\+)") | RE(r"\-(?!-)")


class PostfixOperator(_BaseGrammar):
    grammar = L("++") | L("--")


class BinaryOperator(_BaseGrammar):
    grammar = (
        L("=") | L(":") | L("<") | L(">") | L("<=") | L(">=") | L("==") | L("!=") | L("<>") |
        SignOperator |
        L("*") | L("/") |
        L("&") | L("|") | L("&&") | L("||") |
        L(",")
    )


class FieldOperator(_BaseGrammar):
    grammar = L("->") | L("~>")


class ItemBase(_BaseGrammar):
    grammar = (
        (
            REF("Function") | REF("ArrayElement") | REF("List") | REF("SymbolList") | REF("CurlyList") |
            Bool | Identifier | Symbol | Number | String
        ),
        ZERO_OR_MORE(OPTIONAL(WHITESPACE), FieldOperator, OPTIONAL(WHITESPACE), Identifier),
        ZERO_OR_MORE(SignSymbol, REF("ItemBase")),
    )

    def grammar_elem_init(self, sessiondata):
        if (len(self[1].elements) + len(self[2].elements)) == 0:
            ast = self[0].ast
            value = self[0].value
        else:
            ast = [self[0].ast]
            value = [self[0].value]
            for _, op, _, ident in self[1]:
                ast += [op.string, ident.ast]
                value += [op.string, ident.value]
            for op, ident in self[2]:
                ast += [op.string, ident.ast]
                value += [op.string, ident.value]
        self.ast = {"ItemBase": ast}
        self.value = value


class Item(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = ZERO_OR_MORE(PrefixOperator), ItemBase, ZERO_OR_MORE(PostfixOperator)

    def grammar_elem_init(self, sessiondata):
        if len(self[0].elements) == 0 and len(self[2].elements) == 0:
            ast = self[1].ast
            value = self[1].value
        else:
            ast = [*[op.string for op in self[0]], self[1].ast, *[op.string for op in self[2]]]
            value = [*[op.string for op in self[0]], self[1].value, *[op.string for op in self[2]]]
            # Collapse a sign with a number
            for i in range(len(value)-1):
                v = value[i]
                v2 = value[i+1]
                # Join sign with number
                if (v in ("+", "-")) and isinstance(v2, (int, float)):
                    value[i:i+2] = [v2 if v == "+" else -v2]
                    if len(value) == 1:
                        value = value[0]
                    break
        self.ast = {"Item": ast}
        self.value = value


class Expression(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = Item, ZERO_OR_MORE(BinaryOperator, Item)

    def grammar_elem_init(self, sessiondata):
        if len(self[1].elements) == 0:
            ast = self[0].ast
            value = self[0].value
        else:
            ast = [self[0].ast]
            value = [self[0].value]
            for op, item in self[1]:
                ast += [op.string, item.ast]
                value += [op.string, item.value]
        self.ast = {"Expression": ast}
        self.value = value


class List(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = L("("), ZERO_OR_MORE(Expression), L(")")

    def grammar_elem_init(self, sessiondata):
        # Convert list to function if name of first identifier is in _value4function_table
        # and not in the _dont_convert_list
        isfunction = (
            (len(self[1].elements) > 0)
            and (type(self[1][0].value) is str)
            and (self[1][0].value in sessiondata["value4funcs"])
            and (self[1][0].value not in sessiondata["dont_convert"])
        )
        if not isfunction:
            self.value = [elem.value for elem in self[1]]
            self.ast = {"List": [elem.ast for elem in self[1]]}
        else:
            name = self[1][0].value
            elems = [elem.value for elem in self[1].elements[1:]]
            func = sessiondata["value4funcs"][name]
            if type(func) == tuple:
                func, kwargs = func
            else:
                kwargs = {}
            self.value = {name: func(elems, functionname=name, **kwargs)}

            self.ast = {"ListFunction": {
                "name": name,
                "args": [elem.ast for elem in self[1].elements[1:]],
            }}


class SymbolList(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = L("'("), ZERO_OR_MORE(Expression), L(")")

    def grammar_elem_init(self, sessiondata):
        self.value = [elem.value for elem in self[1]]
        self.ast = {"SymbolList": [elem.ast for elem in self[1]]}


class CurlyList(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = L("{"), ZERO_OR_MORE(Expression), L("}")

    def grammar_elem_init(self, sessiondata):
        self.value = {"{}": [elem.value for elem in self[1]]}
        self.ast = {"CurlyList": [elem.ast for elem in self[1]]}


class Function(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = RE(r"[a-zA-Z][a-zA-Z0-9_]*\("), ZERO_OR_MORE(Expression), L(')')

    def grammar_elem_init(self, sessiondata):
        name = self[0].string[:-1]
        elems = [elem.value for elem in self[1]]
        try:
            func = sessiondata["value4funcs"][name]
        except KeyError:
            self.value = {name: elems}
        else:
            if type(func) == tuple:
                func, kwargs = func
            else:
                kwargs = {}
            self.value = {name: func(elems, functionname=name, **kwargs)}

        self.ast = {"Function": {
            "name": name,
            "args": [elem.ast for elem in self[1]]
        }}


class ArrayElement(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = RE(r"[a-zA-Z][a-zA-Z0-9_]*\["), Expression, L(']')

    def grammar_elem_init(self, sessiondata):
        name = self[0].string[:-1]
        self.value = {"Array:"+name: self[1].value}
        self.ast = {"ArrayElem": {
            "name": name,
            "elem": self[1].ast
        }}


class SkillFile(_BaseGrammar):
    grammar_whitespace_mode = "optional"
    grammar = ONE_OR_MORE(Expression), OPTIONAL(WHITESPACE)

    def grammar_elem_init(self, sessiondata):
        self.ast = {"SkillFile": [elem.ast for elem in self[0]]}
        self.value = {"SkillFile": [elem.value for elem in self[0]]}

    @classmethod
    def parser(cls, sessiondata=None, *args, **kwargs):
        if ((sessiondata is None)
            or not all(s in sessiondata for s in ("value4funcs", "dont_convert"))
        ):
            raise Exception("{0}.parser() called directly; use {0}.parse_string()".format(
                cls.__name__
            ))
        return super().parser(sessiondata=sessiondata, *args, **kwargs)

    @classmethod
    def parse_string(cls, text, *, value4funcs={}, dont_convert=[]):
        fs = _builtins.copy()
        fs.update(value4funcs)
        sessiondata = {
            "value4funcs": fs,
            "dont_convert": dont_convert,
        }

        p = cls.parser(sessiondata=sessiondata)
        return p.parse_string(text)
