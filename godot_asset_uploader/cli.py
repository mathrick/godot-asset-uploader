from functools import reduce
from textwrap import dedent
from typing import Sequence

import click, cloup
from click.core import ParameterSource
import cloup.constraints
from cloup.constraints import (
    IsSet, AnySet, Constraint as CloupConstraint, BoundConstraintSpec,
    Rephraser as CloupRephraser, require_all,
    UnsatisfiableConstraint, ConstraintViolated,
)
from cloup.constraints._support import BoundConstraint
from cloup.constraints.conditions import Predicate, ensure_constraints_support
from cloup.constraints.common import (
    format_param, format_param_list, get_param_name,
    get_params_whose_value_is_set, param_value_is_set
)
from cloup._util import make_repr

from .util import dict_merge, ensure_sequence, batched, prettyprint_list
from .evil import patch_function_code


def readable_param_name(param):
    prefix = "" if param.param_type_name == "argument" else "--"
    return f"{prefix}{param.human_readable_name}"

def is_default_param(ctx, param):
    return not (source := ctx.get_parameter_source(param)) or source in [
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    ]

def required_if_missing(names, * dependents, lenient=True):
    if not isinstance(names, Predicate):
        names = ensure_sequence(names)
        names = (LenientAnySet if lenient else AnySet)(*names)
    return If(names, then=optional,
              else_=RequireNamed(*dependents) if dependents else require_all)

def as_predicate(thing):
    if isinstance(thing, Predicate):
        return thing
    if isinstance(thing, str):
        return LenientIsSet(thing)
    if isinstance(thing, Sequence):
        return LenientAnySet(*thing)
    raise TypeError(f"Don't know how to convert {thing} to a Cloup predicate")

def is_param_constrained_by(param, constraint, ctx):
    if isinstance(constraint, (BoundConstraint, BoundConstraintSpec)):
        constraint = constraint.constraint
    for constr in ctx.command.all_constraints:
        if constr.constraint is constraint and param in constr.params:
            return True
    return False

def get_param_constraints(param, ctx):
    return [constr.constraint for constr in ctx.command.all_constraints
            if is_param_constrained_by(param, constr, ctx)]

def maybe_invoke_with_ctx(self, value):
    if callable(value):
        try:
            ctx = click.get_current_context()
            return value(self, ctx)
        except RuntimeError:
            pass
    return value

class QueryPromptMixin:
    @property
    def prompt(self):
        return maybe_invoke_with_ctx(self, getattr(self, "_prompt", None))

    @prompt.setter
    def prompt(self, value):
        if callable(getattr(self, "_prompt", None)) and not callable(value):
            return
        self._prompt = value


class QueryRequiredMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Needed for our hacky Constraint.auto_require() business
        self.parsing_started = False

    def consume_value(self, ctx, opts):
        self.parsing_started = True
        return super().consume_value(ctx, opts)

    @property
    def required(self):
        return maybe_invoke_with_ctx(self, getattr(self, "_required", None))

    @required.setter
    def required(self, value):
        if callable(getattr(self, "_required", None)) and not callable(value):
            return
        self._required = value


class DynamicPromptOption(QueryPromptMixin, QueryRequiredMixin, cloup.Option):
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


class ConstraintQueryMixin:
    """cloup.Constraint mix-in which implements a protocol by which
parameter's required status can be dynamically queried."""
    def is_required(self, param, ctx):
        raise NotImplementedError

    def is_allowed(self, param, ctx):
        raise NotImplementedError

    def check_values(self, params, ctx):
        try:
            return all(
                param_value_is_set(p, ctx.params[p.name]) for p in params if self.is_required(p, ctx)
            ) and all(
                self.is_allowed(p, ctx) for p in get_params_whose_value_is_set(params, ctx.params)
            )
        except NotImplementedError:
            return super().check_values(params, ctx)

    @classmethod
    def auto_prompter(cls, text=None, /, when="required"):
        if when not in ["required", "always"]:
            raise ValueError(
                f"Invalid value for 'when' ('{when}'), allowed values are 'required' and 'always'"
            )

        def prompter(param, ctx):
            if isinstance(cls, type):
                constraints = get_param_constraints(param, ctx)
            else:
                constraints = [cls]
            if not constraints:
                return None
            if (when == "always" or any(c.is_required(param, ctx) for c in constraints)) \
               and all(c.is_allowed(param, ctx) for c in constraints):
                return text or param.name.capitalize()

        return prompter

    @classmethod
    def auto_require(cls):
        def require(param, ctx):
            if isinstance(cls, type):
                constraints = get_param_constraints(param, ctx)
            else:
                constraints = [cls]
            # NB: we don't do the computations until we have
            # param.parsing_started, otherwise things like
            # accept_none.consistency_checks get unhappy because they might get
            # required=True on some unexpected arguments, depending on how
            # conditions are set up
            if not constraints or not param.parsing_started:
                return None
            return any(
                c.is_required(param, ctx) for c in constraints
            ) and all(
                c.is_allowed(param, ctx) for c in constraints
            )

        return require


class LenientParamSetMixin():
    """A mixin for AnySet and AllSet which makes them not complain if the
listed options do not exist in the current command"""
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
    # Unfortunately had to copy these from AnySet because they need tweaks
    def __call__(self, ctx: click.Context) -> bool:
        command = ensure_constraints_support(ctx.command)
        params = []
        for param in self.param_names:
            try:
                params.append(command.get_param_by_name(param))
            except KeyError:
                pass
        return any(param_value_is_set(param, ctx.params.get(get_param_name(param)))
                   for param in params)

    def __or__(self, other: Predicate) -> Predicate:
        if isinstance(other, AnySet):
            return LenientAnySet(*self.param_names, *other.param_names)
        return super().__or__(other)

class LenientIsSet(LenientParamSetMixin, IsSet):
    def _adjust_param_names(self, ctx):
        return self.param_name in ctx.command._params_by_name


class ConstraintMixin(ConstraintQueryMixin):
    def rephrased(self, help=None, error=None):
        return Rephraser(self, help, error)

    def hidden(self):
        return Rephraser(self, help="")


class Constraint(ConstraintMixin, CloupConstraint):
    def rephrased(self, help=None, error=None):
        return Rephraser(self, help, error)

    def hidden(self):
        return Rephraser(self, help="")


class Rephraser(CloupRephraser):
    def is_required(self, param, ctx):
        return self.constraint.is_required(param, ctx)

    def is_allowed(self, param, ctx):
        return self.constraint.is_allowed(param, ctx)


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
        names = self._format_names(self.names, ctx)
        return f"{names} are required" if len(self.names) > 1 else f"{names} is required"

    def check_consistency(self, params):
        param_names = set([param.name for param in params])
        if not set(self.names) <= param_names:
            missing = param_names - set(self.names)
            reason = (
                f"the constraint requires parameters {prettyprint_list(missing)}, "
                f"which have not been declared"
            )
            raise UnsatisfiableConstraint(self, params, reason)

    def check_values(self, params, ctx):
        given = get_params_whose_value_is_set(params, ctx.params)
        if not set(self.names) <= set([p.name for p in given]):
            missing = [p for p in params if p not in given and p.name in self.names]
            raise ConstraintViolated(
                f"the following parameters are required:\n"
                f"{format_param_list(missing)}",
                ctx=ctx, constraint=self, params=params,
            )

    def is_required(self, param, ctx) -> None:
        return param.name in self.names

    def is_allowed(self, param, ctx) -> None:
        return True


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
        cond, branch = self.current_branch(ctx)
        if not branch:
            return
        try:
            branch.check_values(params, ctx)
        except ConstraintViolated as err:
            msg = "when {desc}, {err}".format(
                desc=cond.description(ctx), err=err
            ) if cond else f"no conditions were satisfied, and {err}"

            raise ConstraintViolated(
                msg, ctx=ctx, constraint=self, params=params
            )

    def current_branch(self, ctx):
        for cond, branch in self._conditions:
            if not cond or cond(ctx):
                return cond, branch
        return None, None

    def is_required(self, param, ctx) -> None:
        _, branch = self.current_branch(ctx)
        if branch:
            return branch.is_required(param, ctx)
        return False

    def is_allowed(self, param, ctx) -> None:
        _, branch = self.current_branch(ctx)
        if branch:
            return branch.is_allowed(param, ctx)
        return True

    def __repr__(self) -> str:
        args = [{f"condition{i}" if cond else "else_": cond,
                 f"branch{i}": branch}
                for i, (cond, branch) in enumerate(self._conditions)]
        return make_repr(self, **reduce(dict_merge, args, {}))


class If(Cond):
    def __init__(self, condition, then, else_=None):
        super().__init__(condition, then, else_=else_)


class RequireAll(ConstraintQueryMixin, type(require_all)):
    def is_required(self, param, ctx) -> None:
        return is_param_constrained_by(param, self, ctx)

    def is_allowed(self, param, ctx) -> None:
        return True

require_all = RequireAll()


class RequireAtLeast(ConstraintMixin, cloup.constraints.RequireAtLeast):
    def is_required(self, param, ctx):
        params = []
        for constr in ctx.command.all_constraints:
            if constr.constraint is self and param in constr.params:
                params = constr.params
        count_set = len([p for p in params
                         if param_value_is_set(p, ctx.params.get(p.name))])
        return count_set < self.min_num_params

    def is_allowed(self, param, ctx):
        return True

optional = RequireAtLeast(0).rephrased("optional")


class AcceptAtMost(ConstraintMixin, cloup.constraints.AcceptAtMost):
    def is_required(self, param, ctx):
        return False

    def is_allowed(self, param, ctx):
        params = []
        for constr in ctx.command.all_constraints:
            if constr.constraint is self and param in constr.params:
                params = constr.params
        count_set = len([p for p in params
                         if param_value_is_set(p, ctx.params.get(p.name))])
        return count_set < self.max_num_params

accept_none = AcceptAtMost(0)

@patch_function_code(
    cloup.constraints.common.param_value_by_name,
    dedent("""\
    def param_value_by_name(ctx: Context, name: str) -> Any:
        try:
            return ctx.params[name]
        except KeyError:
            raise KeyError(f'"{name}" is not the name of a CLI parameter')
    """)
)
def param_value_by_name(ctx, name):
    return ctx.params.get(name)
