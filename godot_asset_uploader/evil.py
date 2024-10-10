"""Evil, no good hacks (ie. monkey-patching code object of existing functions)"""

import difflib
from inspect import getsource

FunctionType = type(lambda: 42)

def patch_function_code(target, expected_source):
    assert isinstance(target, FunctionType), \
        f"Target to patch_function_code() must be a function, but got {type(target)}"

    if (actual := getsource(target)) != expected_source:
        diff = "\n".join("    " + line
                       for line in difflib.unified_diff(
                               expected_source.splitlines(),
                               actual.splitlines(),
                               fromfile='expected',
                               tofile='actual'
                       ))
        raise ValueError(f"Source code for '{target.__name__}' differs from expected:\n{diff}")

    def patcher(func):
        target.__code__ = func.__code__
        return func

    return patcher
