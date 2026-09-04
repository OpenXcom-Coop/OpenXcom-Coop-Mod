"""TFTD (xcom2 master) user-dir helper for the coop harness.

The stock make_user_dir pins the xcom1 master and drops saves in xcom1/. TFTD
coop repros need the xcom2 master plus the submods a real TFTD save was made
with, and saves live in xcom2/. This mirrors make_user_dir but for TFTD.
"""

import os
import shutil

import harness

# The mods a stock TFTD nightly campaign carries (order = load order). xcom2 is
# the master; the rest are shipped standard submods activated by id.
TFTD_MODS = [
    "xcom2",
    "Smarter_Equip_TFTD",
    "StrategyCore_Swap_Small_USOs_TFTD",
    "UFOextender_Gun_Melee_TFTD",
    "UFOextender_Psionic_Line_Of_Fire_TFTD",
    "XcomUtil_High_Explosive_Damage_TFTD",
    "XcomUtil_Improved_Gauss",
    "XcomUtil_Starting_Defensive_Improved_Base_TFTD",
]

TFTD_OPTIONS = """\
mods:
{mods}options:
  displayWidth: 640
  displayHeight: 400
  fullscreen: false
  borderless: false
  captureMouse: false
  playIntro: false
  musicVolume: 0
  soundVolume: 0
  uiVolume: 0
"""


def make_tftd_user_dir(name, saves=(), options=None, mods=TFTD_MODS):
    name = "s%d_%s" % (harness.HARNESS_SLOT, name)
    d = os.path.join(harness.TEST_ROOT, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "xcom2"))
    modblock = "".join("  - active: true\n    id: %s\n" % m for m in mods)
    opts = TFTD_OPTIONS.format(mods=modblock)
    if options:
        extra_opts = ""
        for key, value in options.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            extra_opts += "  %s: %s\n" % (key, value)
        opts = opts.replace("options:\n", "options:\n" + extra_opts, 1)
    with open(os.path.join(d, "options.cfg"), "w", encoding="utf-8") as f:
        f.write(opts)
    for save in saves:
        shutil.copy(save, os.path.join(d, "xcom2"))
    return d
