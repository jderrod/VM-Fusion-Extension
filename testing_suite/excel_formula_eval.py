"""
excel_formula_eval.py — minimal Excel formula evaluator (stdlib only).

Supports the subset of Excel used by the 'Panel Calculated Values' sheet:
  IF, AND, OR, NOT; comparisons (=, <>, <, >, <=, >=); arithmetic (+ - * /);
  parentheses; string literals; named references.

Implements the Excel semantics that matter here:
  - blank (None) behaves as 0 in arithmetic/numeric comparison and equals ""
  - string comparison is case-insensitive
  - IF condition: nonzero number / TRUE is truthy, blank is falsy
"""

import re

_TOKEN_RE = re.compile(r"""
    \s+
  | (?P<num>\d+\.\d*|\.\d+|\d+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<name>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><>|<=|>=|[=<>+\-*/(),&])
""", re.VERBOSE)


def tokenize(formula):
    tokens = []
    pos = 0
    s = formula.strip()
    if s.startswith("="):
        s = s[1:]
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise ValueError(f"Cannot tokenize at: {s[pos:pos+20]!r}")
        pos = m.end()
        if m.group("num") is not None:
            tokens.append(("num", float(m.group("num"))))
        elif m.group("str") is not None:
            raw = m.group("str")[1:-1].replace('""', '"')
            tokens.append(("str", raw))
        elif m.group("name") is not None:
            tokens.append(("name", m.group("name")))
        elif m.group("op") is not None:
            tokens.append(("op", m.group("op")))
    return tokens


# ─── Excel value semantics ───────────────────────────────────────────────────

def _num(v):
    """Coerce to number the way Excel does in arithmetic context."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    raise ValueError(f"Expected number, got {v!r}")


def _truthy(v):
    if v is None or v == "":
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        if v.strip().upper() == "TRUE":
            return True
        if v.strip().upper() == "FALSE":
            return False
        raise ValueError(f"Cannot use string {v!r} as condition")
    return bool(v)


def _is_text(v):
    return isinstance(v, str) and not isinstance(v, bool)


def xl_equal(a, b):
    """Excel '=' comparison. Blank equals blank, "", 0, and FALSE.
    Text comparison is case-insensitive."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        blank, other = (a, b) if a is None else (b, a)
        if _is_text(other):
            return other == ""
        return _num(other) == 0.0
    if _is_text(a) and _is_text(b):
        return a.casefold() == b.casefold()
    if _is_text(a) != _is_text(b):
        return False  # text never equals number in Excel
    return _num(a) == _num(b)


def xl_less(a, b):
    """Excel '<' comparison. Numbers < text; blank behaves like 0 / ''."""
    a_text = _is_text(a)
    b_text = _is_text(b)
    if a is None:
        a_text = b_text  # blank chameleons to the other side's type
        a = "" if b_text else 0
    if b is None:
        b_text = a_text
        b = "" if a_text else 0
    if a_text and b_text:
        return a.casefold() < b.casefold()
    if a_text != b_text:
        return not a_text  # any number is less than any text
    return _num(a) < _num(b)


# ─── Parser / evaluator ──────────────────────────────────────────────────────

class Evaluator:
    """
    resolver(name_lowercase) -> value; raises KeyError for unknown names.
    """

    def __init__(self, resolver):
        self.resolver = resolver

    def eval(self, formula):
        # Re-entrant: resolving a name mid-parse may trigger a nested eval()
        # on this same instance, so save/restore parser state.
        saved = (getattr(self, "tokens", None), getattr(self, "i", 0))
        try:
            self.tokens = tokenize(formula)
            self.i = 0
            val = self._comparison()
            if self.i != len(self.tokens):
                raise ValueError(f"Unexpected token: {self.tokens[self.i]}")
            return val
        finally:
            self.tokens, self.i = saved

    def _peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def _next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _expect_op(self, op):
        kind, val = self._next()
        if kind != "op" or val != op:
            raise ValueError(f"Expected '{op}', got {val!r}")

    def _comparison(self):
        left = self._concat()
        while True:
            kind, val = self._peek()
            if kind == "op" and val in ("=", "<>", "<", ">", "<=", ">="):
                self._next()
                right = self._concat()
                if val == "=":
                    left = xl_equal(left, right)
                elif val == "<>":
                    left = not xl_equal(left, right)
                elif val == "<":
                    left = xl_less(left, right)
                elif val == ">":
                    left = xl_less(right, left)
                elif val == "<=":
                    left = not xl_less(right, left)
                else:  # >=
                    left = not xl_less(left, right)
            else:
                return left

    def _concat(self):
        left = self._additive()
        while True:
            kind, val = self._peek()
            if kind == "op" and val == "&":
                self._next()
                right = self._additive()

                def _text(v):
                    if v is None:
                        return ""
                    if isinstance(v, bool):
                        return "TRUE" if v else "FALSE"
                    if isinstance(v, float) and v == int(v):
                        return str(int(v))
                    return str(v)

                left = _text(left) + _text(right)
            else:
                return left

    def _additive(self):
        left = self._multiplicative()
        while True:
            kind, val = self._peek()
            if kind == "op" and val in ("+", "-"):
                self._next()
                right = self._multiplicative()
                left = _num(left) + _num(right) if val == "+" else _num(left) - _num(right)
            else:
                return left

    def _multiplicative(self):
        left = self._unary()
        while True:
            kind, val = self._peek()
            if kind == "op" and val in ("*", "/"):
                self._next()
                right = self._unary()
                left = _num(left) * _num(right) if val == "*" else _num(left) / _num(right)
            else:
                return left

    def _unary(self):
        kind, val = self._peek()
        if kind == "op" and val == "-":
            self._next()
            return -_num(self._unary())
        if kind == "op" and val == "+":
            self._next()
            return _num(self._unary())
        return self._primary()

    def _primary(self):
        kind, val = self._next()
        if kind == "num":
            return val
        if kind == "str":
            return val
        if kind == "op" and val == "(":
            inner = self._comparison()
            self._expect_op(")")
            return inner
        if kind == "name":
            nkind, nval = self._peek()
            if nkind == "op" and nval == "(":
                return self._function(val)
            upper = val.upper()
            if upper == "TRUE":
                return True
            if upper == "FALSE":
                return False
            return self.resolver(val.lower())
        raise ValueError(f"Unexpected token {val!r}")

    def _function(self, fname):
        self._expect_op("(")
        args = []
        kind, val = self._peek()
        if kind == "op" and val == ")":
            self._next()
        else:
            while True:
                args.append(self._comparison())
                kind, val = self._next()
                if kind == "op" and val == ")":
                    break
                if not (kind == "op" and val == ","):
                    raise ValueError(f"Expected ',' or ')' in {fname}(), got {val!r}")

        f = fname.upper()
        if f == "IF":
            if len(args) == 2:
                return args[1] if _truthy(args[0]) else False
            return args[1] if _truthy(args[0]) else args[2]
        if f == "AND":
            return all(_truthy(a) for a in args)
        if f == "OR":
            return any(_truthy(a) for a in args)
        if f == "NOT":
            return not _truthy(args[0])
        if f == "MIN":
            return min(_num(a) for a in args)
        if f == "MAX":
            return max(_num(a) for a in args)
        if f == "ROUND":
            import decimal
            d = decimal.Decimal(str(_num(args[0])))
            places = int(_num(args[1])) if len(args) > 1 else 0
            return float(d.quantize(decimal.Decimal(10) ** -places,
                                    rounding=decimal.ROUND_HALF_UP))
        if f == "ABS":
            return abs(_num(args[0]))
        raise ValueError(f"Unsupported function: {fname}")
