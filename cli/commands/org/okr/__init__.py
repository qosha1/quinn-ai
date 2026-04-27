"""qn org okr command group.

Commands for managing OKRs (Objectives and Key Results) via beads.
OKRs are beads epic issues with the 'okr' label.

Public surface re-exports okr_cmd so existing
'from cli.commands.org.okr import okr_cmd' import sites keep working.
Subcommand impls live in:
- _helpers.py  shared run_bd re-export + _create_okr (also where tests
               that previously patched 'cli.commands.org.okr.run_bd' should
               now patch 'cli.commands.org.okr._helpers.run_bd')
- list_cmd.py  list
- manage.py    set, add, link
- inspect.py   cascade, show, progress, update-kr
"""

import click

from . import inspect, list_cmd, manage
from ._helpers import _create_okr, run_bd  # noqa: F401 — public re-exports


@click.group()
def okr_cmd():
    """Manage organization OKRs.

    OKRs are tracked as beads issues with type 'okr'.
    Work items link to OKRs via 'serves' dependency.
    """
    pass


# Register subcommands on the group
list_cmd.register(okr_cmd)
manage.register(okr_cmd)
inspect.register(okr_cmd)


__all__ = ["okr_cmd"]
