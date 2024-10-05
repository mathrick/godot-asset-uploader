import click, cloup
from click.core import ParameterSource
from cloup.constraints import (
    Constraint, UnsatisfiableConstraint, ConstraintViolated,
)
from cloup.constraints.common import format_param_list, get_params_whose_value_is_set

from .util import ensure_sequence, prettyprint_list


def readable_param_name(param):
    prefix = "" if param.param_type_name == "argument" else "--"
    return f"'{prefix}{param.human_readable_name}'"

def is_default_param(ctx, param):
    return ctx.get_parameter_source(param) in [
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    ]


class DynamicPromptOption(cloup.Option):
    "Allow disabling prompting through command-line switch"
    def prompt_for_value(self, ctx):
        assert self.prompt is not None
        if ctx.obj.no_prompt:
            return self.get_default(ctx)
        else:
            return super().prompt_for_value(ctx)


class OptionRequiredIfMissing(DynamicPromptOption):
    """Dependent option which is required if the context does not have
specified option(s) set"""

    def __init__(self, *args, **kwargs):
        try:
            options = ensure_sequence(kwargs.pop("required_if_missing"))
        except KeyError:
            raise KeyError(
                "OptionRequiredIfMissing needs the required_if_missing keyword argument"
            )

        super().__init__(*args, **kwargs)
        self._options = options

    def process_value(self, ctx, value):
        required = not any(ctx.params.get(opt) for opt in self._options)
        dep_value = super().process_value(ctx, value)
        if required and dep_value is None:
            opt_names = [readable_param_name(p) for p in ctx.command.params
                         if p.name in self._options]
            # opt_names might be empty, e.g. if the only option is 'url' and
            # it's not taken by the currently processed command
            msg = f"Required unless one of {', '.join(opt_names)} is provided" if opt_names else None
            raise click.MissingParameter(ctx=ctx, param=self, message=msg)
        return value


class PriorityOptionParser(click.OptionParser):
    """Order of proessing and grabbing defaults for options is very important for
the UI, since a lot of things depend on previous values. This allows us to
ensure the order is correct and preserved, no matter how the user invokes us"""
    def __init__(self, ctx, priority_list, priority_adjustments=None):
        self.order = list(ctx.command.params)
        all_params = {p.name: p for p in self.order}
        priority_adjustments = [[all_params[name] for name in adjustment if name in all_params]
                                for adjustment in priority_adjustments or []]
        for adjustment in priority_adjustments:
            # We're trying to nudge the order just enough to satisfy the
            # ordering in the current adjustment without affecting other
            # elements. To do this, we create the list of *current* indexes of
            # the relevant params in ctx.params, then sort it. Then we insert
            # each param in turn in the given spot in the list
            indexes = [self.order.index(p) for p in adjustment]
            for param, slot in zip(adjustment, sorted(indexes)):
                self.order[slot] = param
        # Finally, things in priority list just go into the front unconditionally
        self.order = [
            all_params[param] for param in priority_list if param in all_params
        ] + [p for p in self.order if p.name not in priority_list]
        super().__init__(ctx)

    def parse_args(self, args):
        opts, args, order = super().parse_args(args)
        return (opts, args, self.order)


class PriorityProcessingCommand(cloup.Command):
    PRIORITY_LIST = []
    PRIORITY_ADJUSTMENTS = []

    def make_parser(self, ctx):
        parser = PriorityOptionParser(ctx, self.PRIORITY_LIST, self.PRIORITY_ADJUSTMENTS)
        for param in self.get_params(ctx):
            param.add_to_parser(parser, ctx)
        return parser


class RequireNamed(Constraint):
    """Cloup constraint requiring the listed parameters"""
    def __init__(self, *names):
        self.names = names

    def _format_names(self, names, ctx):
        params = ctx.command.params
        param_names = [p.name for p in params]
        param_names = [readable_param_name(params[param_names.index(name)])
                       if name in param_names else name
                       for name in names]
        return prettyprint_list(param_names)

    def help(self, ctx: click.Context) -> str:
        return f"parameters {self._format_names(self.names, ctx)} required"

    def check_values(self, params, ctx):
        given = get_params_whose_value_is_set(params, ctx.params)
        if not set(self.names) <= set([p.name for p in given]):
            missing = [p for p in params if p not in given and p.name in self.names]
            raise ConstraintViolated(
                f"the following parameters are required:\n"
                f"{format_param_list(missing)}",
                ctx=ctx, constraint=self, params=params,
            )

    def check_consistency(self, params):
        params = set([param.name for param in params])
        names = set(self.names)
        if not names <= params:
            missing = params - names
            reason = (
                f"the constraint requires parameters {prettyprint_list(names)}, "
                f"which have not been declared"
            )
            raise UnsatisfiableConstraint(self, params, reason)
