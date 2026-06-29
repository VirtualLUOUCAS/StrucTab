"""
Reward configuration for Uni-TabRL.

The overall reward follows the paper's decomposed formulation:

    R = lambda_1 * R_validity + lambda_2 * R_structure + lambda_3 * R_content

Two orthogonal axes control which structure / content reward is used, so that
every ablation row in the paper (Table "Effectiveness of Uni-TabRL") can be
reproduced by setting two environment variables:

    STRUCTURE_REWARD     CONTENT_REWARD     -> paper setting
    ----------------     --------------        ------------------------------
    teds_s               teds                  (a) RL baseline
    teds_s               vlm_judge             (b) + VLM judge
    teds_s               anchor                (c) + Anchor-Guided Destylization
    1d_probe             teds                  (d) + 1D Probe
    1d_probe             anchor                (e) StrucTab (final)
"""

import os

# --- Reward weights (lambda_1, lambda_2, lambda_3), as reported in the paper ---
VALIDITY_WEIGHT = float(os.getenv("VALIDITY_WEIGHT", "0.4"))
STRUCTURE_WEIGHT = float(os.getenv("STRUCTURE_WEIGHT", "0.3"))
CONTENT_WEIGHT = float(os.getenv("CONTENT_WEIGHT", "0.3"))

# --- Structure reward variant ---
#   "teds_s"   : holistic structure-only TEDS (baseline)
#   "1d_probe" : proposed 1D Probe structural reward
STRUCTURE_REWARD = os.getenv("STRUCTURE_REWARD", "1d_probe").lower()

# --- Content reward variant ---
#   "teds"      : raw TEDS on the original prediction (baseline)
#   "vlm_judge" : VLM-as-judge visual consistency between rendered tables
#   "anchor"    : proposed Anchor-Guided Destylization
CONTENT_REWARD = os.getenv("CONTENT_REWARD", "anchor").lower()

_STRUCTURE_CHOICES = {"teds_s", "1d_probe"}
_CONTENT_CHOICES = {"teds", "vlm_judge", "anchor"}

assert STRUCTURE_REWARD in _STRUCTURE_CHOICES, f"Invalid STRUCTURE_REWARD: {STRUCTURE_REWARD}"
assert CONTENT_REWARD in _CONTENT_CHOICES, f"Invalid CONTENT_REWARD: {CONTENT_REWARD}"
