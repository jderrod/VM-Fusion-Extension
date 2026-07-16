"""
Panel expected-output engine.

Faithfully re-implements the derived-parameter formulas from the
"Panel Calculated Values" sheet of
  testing_suite/Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm
so we can recompute the EXPECTED output for any scenario directly from its
input parameters — independently of the sheet's own stored ValidationOutputs
row. Comparing this recomputation against both the stored ValidationOutputs
values and the actual model output (Panel Scenarios/*/P1_all_parameters.json)
gives a three-way check.

Excel semantics replicated:
- string comparison is case-insensitive ("Whole" == "WHOLE")
- a blank cell (None / "") counts as 0 in a numeric comparison, but equals ""
  in a text comparison (Excel's dual nature of empty cells)

KNOWN SHEET QUIRK: the cutout_B_* formulas on the sheet reference cutout_A (not
cutout_B) and the x/y formulas are swapped with y/width. We replicate them
EXACTLY as written (so 'expected_calc' matches what the sheet actually computes)
and flag them, rather than silently "fixing" the ground truth.
"""

# ── Fixed constants (Panel Calculated Values, Dependency=Fixed) ──────────────
COMPONENT_THICKNESS = 0.5
NOTCHING_X_DIST = 0.38
BOTTOM_NOTCHING_STANDARD_Y_DIST = 3.5
SHOE_HEIGHT = 4.0
SHOE_TOP_NOTCH_GAP = 0.5

# B_* cutout dimension lookup table: group -> (width, height, y_dist_from_floor,
# x_dist_from_wall). Groups collapse the cutout codes that share dimensions.
_CUTOUT_TABLE = {
    '354':                  {'width': 11.0,  'height': 15.5,   'y': 14.75,  'x': 14.5},
    '386':                  {'width': 11.5,  'height': 10.875, 'y': 18.0,   'x': 28.94},
    '4354':                 {'width': 11.0,  'height': 9.375,  'y': 18.75,  'x': 14.5},
    '347_357':              {'width': 15.5,  'height': 28.875, 'y': 30.125, 'x': 26.0},
    '3471_34715_3571_35715':{'width': 15.5,  'height': 28.875, 'y': 18.0,   'x': 21.0},
}

# cutout code -> group key
_CUTOUT_CODE_GROUP = {
    'B-354': '354',
    'B-386': '386',
    'B-4354': '4354',
    'B-347': '347_357', 'B-357': '347_357',
    'B-3471': '3471_34715_3571_35715', 'B-34715': '3471_34715_3571_35715',
    'B-3571': '3471_34715_3571_35715', 'B-35715': '3471_34715_3571_35715',
}

# Fixed constants the model should hold, per the calc sheet. Validating these
# against the CSV catches drift between the model and the spec (e.g. someone
# edits a B_* cutout dimension in Fusion). Built from the same source values.
def _fixed_constants():
    fc = {
        'component_thickness': COMPONENT_THICKNESS,
        'notching_x_dist': NOTCHING_X_DIST,
        'bottom_notching_standard_y_dist': BOTTOM_NOTCHING_STANDARD_Y_DIST,
        'shoe_height': SHOE_HEIGHT,
        'shoe_top_notch_gap': SHOE_TOP_NOTCH_GAP,
    }
    for grp, dims in _CUTOUT_TABLE.items():
        fc[f'B_{grp}_width'] = dims['width']
        fc[f'B_{grp}_height'] = dims['height']
        fc[f'B_{grp}_y_dist_from_floor'] = dims['y']
        fc[f'B_{grp}_x_dist_from_wall'] = dims['x']
    return fc


FIXED_CONSTANTS = _fixed_constants()

# The derived outputs this engine produces (order matches ValidationOutputs).
DERIVED_PARAMS = [
    'bottom_notching_actual_y_dist',
    'top_notching_y_dist',
    'notching_front_edge_bottom',
    'notching_back_edge_bottom',
    'notching_front_edge_top',
    'notching_back_edge_top',
    'front_notching_activation_offset',
    'back_notching_activation_offset',
    'cutout_A_width', 'cutout_A_height', 'cutout_A_x_coordinate', 'cutout_A_y_coordinate',
    'cutout_B_width', 'cutout_B_height', 'cutout_B_x_coordinate', 'cutout_B_y_coordinate',
]

# Helper-relation derived values that exist on the calc sheet but are NOT
# exported as model parameters — so they have no "actual" to compare against.
HELPER_PARAMS = {
    'front_notching_activation_offset',
    'back_notching_activation_offset',
}

INPUT_PARAMS = [
    'component_height', 'component_width', 'component_floor_clearance',
    'component_ceiling_clearance', 'panel_section',
    # BOTTOM-notch keys off the *inline* stile flags ...
    'panel_abuts_inline_stile_front', 'panel_front_inline_stile_floor_to_ceiling',
    'panel_abuts_inline_stile_back', 'panel_back_inline_stile_floor_to_ceiling',
    # ... TOP-notch keys off the *non-inline* stile flags (the calc sheet used
    # the inline ones here by mistake; the model uses these — confirmed correct
    # for TOP pieces, scenarios 0010/0011/0012/0025).
    'panel_abuts_stile_front', 'panel_front_stile_floor_to_ceiling',
    'panel_abuts_stile_back', 'panel_back_stile_floor_to_ceiling',
    'stile_in_the_back_width', 'cutout_A', 'cutout_B',
]


# ── Excel-semantics helpers ──────────────────────────────────────────────────
def _unquote(x):
    """Fusion stores text parameters wrapped in literal single quotes, so the
    model exports panel_section as "'TOP'" and cutout_A as "'B-386'". Strip the
    surrounding quotes (and whitespace) so lookups/compares work. Non-strings
    pass through unchanged."""
    if not isinstance(x, str):
        return x
    s = x.strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def _blank(x):
    if isinstance(x, str):
        x = _unquote(x)
    return x is None or (isinstance(x, str) and x.strip() == '')


def _num(x):
    """Numeric value with blank-as-0 (Excel numeric context)."""
    if _blank(x):
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _seq(a, b):
    """Excel case-insensitive equality for text (quotes stripped)."""
    return str(_unquote(a)).strip().lower() == str(_unquote(b)).strip().lower()


def _truthy(x):
    """Excel IF() truthiness: nonzero number is TRUE."""
    return _num(x) != 0.0


def _coalesce(primary, fallback):
    """Return primary if it has a value, else fallback (blank-aware)."""
    return fallback if _blank(primary) else primary


def _cutout_dims(code):
    """Return the dimension dict for a cutout code, or None if unmatched/blank."""
    if _blank(code):
        return None
    grp = _CUTOUT_CODE_GROUP.get(str(_unquote(code)).strip())
    return _CUTOUT_TABLE.get(grp) if grp else None


def _section_is_whole_or_bottom(section):
    return _seq(section, 'Whole') or _seq(section, 'Bottom')


# ── The engine ───────────────────────────────────────────────────────────────
def compute_expected(inp):
    """Compute all derived outputs from a scenario's input dict.

    inp keys are the INPUT_PARAMS names (extra keys ignored, missing -> blank).
    Returns {derived_param: value}. Cutout coordinate outputs are numbers when a
    cutout applies, else '' (matching the sheet's "" empty result).
    """
    section = inp.get('panel_section')
    fc = inp.get('component_floor_clearance')
    ceil = inp.get('component_ceiling_clearance')
    # inline flags drive BOTTOM notching
    front = inp.get('panel_abuts_inline_stile_front')
    back = inp.get('panel_abuts_inline_stile_back')
    # TOP notching uses the stile flags too, but the inline and non-inline
    # variants are mutually exclusive per scenario (one set is populated, the
    # other blank), so coalesce: prefer the non-inline value, fall back to the
    # inline one. (The calc sheet used only the inline flags, which is wrong for
    # scenarios that populate the non-inline set — e.g. 0010/0011/0012/0025.)
    front_top = _coalesce(inp.get('panel_abuts_stile_front'), front)
    back_top = _coalesce(inp.get('panel_abuts_stile_back'), back)
    front_top_ftc = _coalesce(inp.get('panel_front_stile_floor_to_ceiling'),
                              inp.get('panel_front_inline_stile_floor_to_ceiling'))
    back_top_ftc = _coalesce(inp.get('panel_back_stile_floor_to_ceiling'),
                             inp.get('panel_back_inline_stile_floor_to_ceiling'))
    stile_back_w = inp.get('stile_in_the_back_width')
    cutout_a = inp.get('cutout_A')

    out = {}

    # bottom_notching_actual_y_dist = (standard + 1) - floor_clearance
    bn_actual = (BOTTOM_NOTCHING_STANDARD_Y_DIST + 1) - _num(fc)
    out['bottom_notching_actual_y_dist'] = bn_actual

    # top_notching_y_dist = IF(ceiling < shoe+gap, (shoe+gap)-ceiling, 0)
    shoe_plus_gap = SHOE_HEIGHT + SHOE_TOP_NOTCH_GAP
    out['top_notching_y_dist'] = (shoe_plus_gap - _num(ceil)) if _num(ceil) < shoe_plus_gap else 0.0

    # notching_front/back_edge_bottom
    bottom_active = (not _seq(section, 'TOP')) and (bn_actual > 0)
    out['notching_front_edge_bottom'] = 1 if (bottom_active and _num(front) == 1) else 0
    out['notching_back_edge_bottom'] = 1 if (bottom_active and _num(back) == 1) else 0

    # notching_front/back_edge_top — AND(section<>"BOTTOM", ceiling < shoe+gap,
    # ceiling <> "") then gate on the NON-INLINE stile flags (per the model).
    top_active = (not _seq(section, 'BOTTOM')) and (_num(ceil) < shoe_plus_gap) and (not _blank(ceil))
    out['notching_front_edge_top'] = 1 if (top_active and _num(front_top) == 1 and _num(front_top_ftc) == 1) else 0
    out['notching_back_edge_top'] = 1 if (top_active and _num(back_top) == 1 and _num(back_top_ftc) == 1) else 0

    # activation offsets = IF(notching_*_edge_bottom, 0, thickness)
    out['front_notching_activation_offset'] = 0.0 if _truthy(out['notching_front_edge_bottom']) else COMPONENT_THICKNESS
    out['back_notching_activation_offset'] = 0.0 if _truthy(out['notching_back_edge_bottom']) else COMPONENT_THICKNESS

    # cutout_A_* : only when section is Whole/Bottom AND cutout_A matches a code
    dims_a = _cutout_dims(cutout_a)
    if _section_is_whole_or_bottom(section) and dims_a is not None:
        out['cutout_A_width'] = dims_a['width']
        out['cutout_A_height'] = dims_a['height']
        out['cutout_A_x_coordinate'] = dims_a['x'] - _num(stile_back_w)
        out['cutout_A_y_coordinate'] = dims_a['y'] - _num(fc)
    else:
        out['cutout_A_width'] = ''
        out['cutout_A_height'] = ''
        out['cutout_A_x_coordinate'] = ''
        out['cutout_A_y_coordinate'] = ''

    # cutout_B_* : the sheet's formulas here are a copy/paste bug — they read
    # cutout_A (not cutout_B) and swap the x/y/width formulas. Since the sheet
    # is not the authority (it's out of date), we compute the INTENDED logic:
    # mirror cutout_A exactly but keyed on the cutout_B code.
    cutout_b = inp.get('cutout_B')
    dims_b = _cutout_dims(cutout_b)
    if _section_is_whole_or_bottom(section) and dims_b is not None:
        out['cutout_B_width'] = dims_b['width']
        out['cutout_B_height'] = dims_b['height']
        out['cutout_B_x_coordinate'] = dims_b['x'] - _num(stile_back_w)
        out['cutout_B_y_coordinate'] = dims_b['y'] - _num(fc)
    else:
        out['cutout_B_width'] = ''
        out['cutout_B_height'] = ''
        out['cutout_B_x_coordinate'] = ''
        out['cutout_B_y_coordinate'] = ''

    return out
