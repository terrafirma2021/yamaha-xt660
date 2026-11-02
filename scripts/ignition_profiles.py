"""Provisional display profile for the recovered early XT660 base-timing maps."""

PROFILE = {
    'id': 'early_xt660_assumed_trigger_10',
    'label': 'Estimated base °BTDC',
    'formula': 'raw*90/256-12.5',
    'slope': 90 / 256,
    'offset': -12.5,
    'trigger_reference_btdc': 10,
    'hardware_verified': False,
    'note': 'Estimated base °BTDC = raw × 90/256 − 12.5. Assumes a 10° BTDC trigger reference and nominal 12-pitch crank geometry; the physical reference is unverified. ECU corrections still apply.',
}
LAYOUTS = {
    'main_u8_A': (0x42AE, 32, 20),
    'main_u8_B': (0x452E, 32, 20),
    'main_u8_C': (0x47AE, 32, 20),
    'correction_surface_D': (0x4A60, 10, 15),
}


def estimated_ignition(m, family='early'):
    """Never infer an angle profile from a title or transfer it to later layouts."""
    layout = LAYOUTS.get(m['id'])
    actual = (int(m['data_address'], 16), m['rows'], m['columns'])
    if family != 'early' or m['element_bytes'] != 1 or layout != actual:
        return None
    return dict(PROFILE)
