"""Shim de compatibilidade que reexporta `backend/sim/physics.py` para os notebooks."""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sim.physics import (  # noqa: E402, F401
    DIRTY_AIR_CUTOFF_S,
    DIRTY_AIR_DECAY_S,
    DIRTY_AIR_MAX_DOWNFORCE_LOSS,
    DIRTY_AIR_MAX_PENALTY_S,
    DRS_GAIN_PER_METER_S,
    DRS_GAP_THRESHOLD_S,
    FUEL_MAX_KG,
    FUEL_SENSITIVITY_S_PER_KG,
    TRACK_TEMP_OPTIMAL,
    TRACK_TEMP_PENALTY_PER_C,
    TYRE_TABLE,
    Compound,
    TyreParams,
    dirty_air_grip_factor,
    dirty_air_time_delta,
    drs_lap_time_gain,
    drs_zone_time_gain,
    fuel_time_delta,
    is_drs_eligible,
    normalize_compound_name,
    tyre_grip,
    tyre_time_loss,
)
