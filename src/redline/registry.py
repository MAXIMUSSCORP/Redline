from __future__ import annotations

from redline.engine import RuleSpec
from redline.rules import (
    ampacity,
    bonding,
    completeness,
    continuous_load,
    fire_alarm,
    panel_demand,
    phase_balance,
    voltage_drop,
)

RULES: tuple[RuleSpec, ...] = (
    ampacity.SPEC,
    continuous_load.SPEC,
    voltage_drop.SPEC,
    bonding.SPEC,
    phase_balance.SPEC,
    panel_demand.SPEC,
    completeness.SPEC,
    fire_alarm.SPEC,
)
