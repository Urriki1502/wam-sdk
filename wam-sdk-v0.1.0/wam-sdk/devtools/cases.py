"""Static case catalog; IDs are the only test identities published in artifacts."""

import unittest

CATALOG = {"selftest": [], "regtest": []}


def case(profile, ident, description):
    def decorate(fn):
        CATALOG[profile].append((ident, description, fn))
        return fn
    return decorate


def suite(profile, context=None):
    items = []
    for ident, description, fn in sorted(CATALOG[profile]):
        test = unittest.FunctionTestCase(lambda f=fn: f(context), description=ident)
        test.case_id = ident
        items.append(test)
    return unittest.TestSuite(items)


def require(condition):
    if not condition:
        raise AssertionError("criterion not met")
