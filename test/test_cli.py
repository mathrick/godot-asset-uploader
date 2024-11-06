import pytest

from godot_asset_uploader.cli import (
    RequireNamed,
)
from test_util import PRETTYPRINT_INPUTS

@pytest.mark.parametrize("input, expected_output", PRETTYPRINT_INPUTS)
def test_require_named_constraint(mocker, input, expected_output):
    params = []
    for name in input:
        param = mocker.Mock(name=name, human_readable_name=name, opts=[f"--{name}"], param_type_name="option")
        # https://docs.python.org/3/library/unittest.mock.html#mock-names-and-the-name-attribute
        param.name = name
        params.append(param)

    ctx = mocker.Mock()
    ctx.command.params = params
    expected_names = expected_output.format(*[f"--{name}" for name in input])
    assert RequireNamed(*input).help(ctx) == (f"{expected_names} are required" if len(input) > 1
                                              else f"{expected_names} is required")
