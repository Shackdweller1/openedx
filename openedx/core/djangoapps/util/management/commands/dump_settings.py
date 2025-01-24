"""
Defines the dump_settings management command.
"""
import inspect
import json
import re
import sys
from datetime import timedelta
from path import Path

from django.conf import settings
from django.core.management.base import BaseCommand


SETTING_NAME_REGEX = re.compile(r'^[A-Z][A-Z0-9_]*$')


class Command(BaseCommand):
    """
    Dump current Django settings to JSON for debugging/diagnostics.

    BEWARE: OUTPUT IS NOT SUITABLE FOR CONSUMPTION BY PRODUCTION SYSTEMS.
    The purpose of this output is to be *helpful* for a *human* operator to understand how their settings are being
    rendered and how they differ between different settings files. The serialization format is NOT perfect: there are
    certain situations where two different settings will output identical JSON. For example, this command does NOT:

    disambiguate between strings and dotted paths to Python objects:
    * some.module.some_function    # <-- an actual function object, which will be printed as...
    * "some.module.some_function"  # <-- a string that is a dotted path to said function object

    disambiguate between lists and tuples:
    * (1, 2, 3)  # <-- this tuple will be printed out as [1, 2, 3]
    * [1, 2, 3]

    disambiguate between sets and sorted lists:
    * {2, 1, 3}  # <-- this set will be printed out as [1, 2, 3]
    * [1, 2, 3]

    disambiguate between internationalized and non-internationalized strings:
    * _("hello") # <-- this will become just "hello"
    * "hello"
    """

    def handle(self, *args, **kwargs):
        """
        Handle the command.
        """
        settings_json = {
            name: _to_json_friendly_repr(getattr(settings, name), f"settings.{name}")
            for name in dir(settings)
            if SETTING_NAME_REGEX.match(name)
        }
        print(json.dumps(settings_json, indent=4))


def _to_json_friendly_repr(value: object, debug_key: str) -> object:
    """
    Turn the value into something that we can print to a JSON file (that is: str, bool, None, int, float, list, dict).

    See the docstring of `Command` for warnings about this function's behavior.
    """
    if isinstance(value, (type(None), bool, int, float, str)):
        # All these types can be printed directly
        return value
    if isinstance(value, (list, tuple, set)):
        if isinstance(value, set):
            # Print sets by sorting them (so that order doesn't matter) into a JSON array.
            elements = sorted(value)
        else:
            # Print both lists and tuples as JSON arrays.
            elements = value
        return [_to_json_friendly_repr(element, f"{debug_key}[{ix}]") for ix, element in enumerate(elements)]
    if isinstance(value, dict):
        # Print dicts as JSON objects
        for subkey in value.keys():
            if not isinstance(subkey, (str, int)):
                raise ValueError(f"Unexpected dict key {subkey} of type {type(subkey)}")
        return {subkey: _to_json_friendly_repr(subval, f"{debug_key}[{subkey!r}]") for subkey, subval in value.items()}
    if isinstance(value, Path):
        # Print path objects as the string `Path('path/to/something')`.
        return repr(value)
    if isinstance(value, timedelta):
        # Print timedelta objects as the string `datetime.timedelta(days=1, ...)`
        return repr(value)
    if proxy_args := getattr(value, "_proxy____args", None):
        # Print gettext_lazy as simply the wrapped string
        if len(proxy_args) == 1:
            if isinstance(proxy_args[0], str):
                return proxy_args[0]
        raise ValueError(f"Not sure how to dump {debug_key} with value {value!r} with proxy args {proxy_args!r}")
    if value is sys.stderr:
        # Print the stderr object as simply "sys.stderr"
        return "sys.stderr"
    try:
        # For anything else, assume it's a function or a class, and try to print its dotted path.
        module = value.__module__
        qualname = value.__qualname__
    except AttributeError:
        # If that doesn't work, then give up--we don't know how to print this value.
        raise ValueError(  # pylint: disable=raise-missing-from
            f"Not sure how to dump {debug_key} with value {value!r} of type {type(value)}"
        )
    if qualname == "<lambda>":
        # Handle lambdas by printing the source lines
        return inspect.getsource(value).strip()
    return f"{module}.{qualname}"
