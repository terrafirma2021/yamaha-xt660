"""Provisional display profiles for the two recovered XT660 firmware families."""

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
    'early': {
        'main_u8_A': (0x42AE, 32, 20),
        'main_u8_B': (0x452E, 32, 20),
        'main_u8_C': (0x47AE, 32, 20),
        'correction_surface_D': (0x4A60, 10, 15),
    },
    'late': {
        'table_38d2': (0x38D2, 32, 20),
        'table_3b52': (0x3B52, 32, 20),
        'table_3dd2': (0x3DD2, 32, 20),
        'table_4084': (0x4084, 10, 15),
    },
}


def estimated_ignition(m, family='early'):
    """Require a byte-sized, address-checked base map in its traced code family."""
    layout = LAYOUTS.get(family, {}).get(m['id'])
    actual = (int(m['data_address'], 16), m['rows'], m['columns'])
    if m['element_bytes'] != 1 or layout != actual:
        return None
    return dict(PROFILE, id=f'{family}_xt660_assumed_trigger_10')
