from functools import reduce
from itertools import chain
from typing import Sequence

import click, cloup
from click.core import ParameterSource
from cloup.constraints import (
    If, IsSet, AnySet, Constraint, UnsatisfiableConstraint, ConstraintViolated,
    require_any, require_all
)
from cloup.constraints.conditions import Predicate
from cloup.constraints.common import format_param, format_param_list, get_params_whose_value_is_set
from cloup._util import make_repr

from .util import dict_merge, ensure_sequence, batched, prettyprint_list

optional = require_any.rephrased("optional")

def readable_param_name(param):
    prefix = "" if param.param_type_name == "argument" else "--"
    return f"{prefix}{param.human_readable_name}"

def is_default_param(ctx, param):
    return ctx.get_parameter_source(param) in [
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    ]

def required_if_missing(names, * dependents, lenient=True):
    if not isinstance(names, Predicate):
        names = ensure_sequence(names)
        names = (LenientAnySet if lenient else AnySet)(*names)
    return If(names, then=optional,
              else_=RequireNamed(*dependents) if dependents else require_all)


class DynamicPromptOption(cloup.Option):
    "Allow disabling prompting through command-line switch"
    def prompt_for_value(self, ctx):
        assert self.prompt is not None
        if ctx.obj.no_prompt:
            return self.get_default(ctx)
        else:
            return super().prompt_for_value(ctx)


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


class LenientParamSetMixin():
    """A mixin for AnySet and AllSet which makes them not complain if the
listed commands do not exist in the current command"""
    # Note: This goes a little into Cloup's internals, so we can avoid
    # rewriting things too much. But it's probably also brittle
    def _adjust_param_names(self, ctx):
        self.param_names = [p for p in self.param_names if p in ctx.command._params_by_name]
        return self.param_names

    def negated_description(self, ctx):
        if not self._adjust_param_names(ctx):
            return ""
        return super().negated_description(ctx)

    def description(self, ctx):
        if not self._adjust_param_names(ctx):
            return ""
        return super().description(ctx)

    def __call__(self, ctx):
        if not self._adjust_param_names(ctx):
            return False
        return super().__call__(ctx)


class LenientAnySet(LenientParamSetMixin, AnySet):
    pass


class LenientIsSet(LenientParamSetMixin, IsSet):
    def _adjust_param_names(self, ctx):
        return self.param_name in ctx.command._params_by_name


class RequireNamed(Constraint):
    """Cloup constraint requiring the listed parameters"""
    def __init__(self, *names):
        self.names = names

    def _format_names(self, names, ctx):
        params = ctx.command.params
        param_names = [p.name for p in params]
        param_names = [format_param(params[param_names.index(name)])
                       if name in param_names else name
                       for name in names]
        return prettyprint_list(param_names)

    def help(self, ctx: click.Context) -> str:
        return f"{self._format_names(self.names, ctx)} are required"

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
        param_names = set([param.name for param in params])
        if not set(self.names) <= param_names:
            missing = param_names - set(self.names)
            reason = (
                f"the constraint requires parameters {prettyprint_list(missing)}, "
                f"which have not been declared"
            )
            raise UnsatisfiableConstraint(self, params, reason)

def as_predicate(thing):
    if isinstance(thing, Predicate):
        return thing
    if isinstance(thing, str):
        return LenientIsSet(thing)
    if isinstance(thing, Sequence):
        return LenientAnySet(*thing)
    raise TypeError(f"Don't know how to convert {thing} to a Cloup predicate")

class Cond(Constraint):
    """Check a series of conditions, and execute the constraint of the
first one that is satisfied. Optionally, an else_ might be given which
will be taken if no other condition is satisfied"""
    def __init__(self, *conditions, else_=None):
        self._conditions = [(as_predicate(cond), branch)
                            for cond, branch in batched(conditions, 2)]
        if else_:
            self._conditions.append((None, else_))

    def help(self, ctx) -> str:
        descriptions = [(f"if {desc} then " if cond else "") + branch.help(ctx)
                        for cond, branch in self._conditions
                        if (desc := not cond or cond.description(ctx))]
        return prettyprint_list(descriptions, sep1=", otherwise ", sep2="; ", sep3="; otherwise ")

    def check_consistency(self, params) -> None:
        for cond, branch in self._conditions:
            branch.check_consistency(params)

    def check_values(self, params, ctx) -> None:
        cond_is_true = None
        for cond, branch in self._conditions:
            if not cond or (cond_is_true := cond(ctx)):
                try:
                    branch.check_values(params, ctx)
                    break
                except ConstraintViolated as err:
                    msg = "when {desc}, {err}".format(
                            desc=cond.description(ctx) if cond_is_true else cond.negated_description(ctx),
                            err=err
                    ) if cond else f"no conditions were satisfied, and {err}"

                    raise ConstraintViolated(
                        msg, ctx=ctx, constraint=self, params=params
                    )

    def __repr__(self) -> str:
        args = [{f"condition{i}" if cond else "else_": cond,
                 f"branch{i}": branch}
                for i, (cond, branch) in enumerate(self._conditions) ]
        return make_repr(self, **reduce(dict_merge, args, {}))
