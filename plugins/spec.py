'''
Fields of the PCB specification (Leiterplattenspezifikation).
Every field is (key, label, choices, default). Choices are suggestions, the combo boxes accept
free text. AUTO fields are read from the board and are not editable.
'''

import os

AUTO = None

SECTIONS = [
    ('ALLGEMEIN', [
        ('basismaterial', 'Basismaterial', ['FR4', 'Aluminium', 'PTFE', 'Polyimid'], 'FR4'),
        ('lagenanzahl', 'Lagenanzahl', AUTO, ''),
        ('abmessungen', 'Abmessungen [mm]', AUTO, ''),
        ('designs', 'Anzahl verschiedener Designs', ['1', '2', '3', '4'], '1'),
        ('liefereinheit', 'Liefereinheit', ['Einzelkarte', 'Nutzen'], 'Einzelkarte'),
    ]),
    ('LEITERPLATTE', [
        ('dicke', 'Leiterplattendicke [mm]', ['0.8', '1.0', '1.2', '1.6', '2.0'], ''),
        ('kupferdicke', 'Kupferdicke [µm]', ['70', '35'], '70'),
        ('materialtyp', 'Materialtyp', ['FR4 TG135', 'FR4 TG150', 'FR4 TG170'], 'FR4 TG135'),
        ('oberflaeche', 'Oberfläche', ['HAL bleifrei', 'chem. Gold (ENIG)', 'ENEPIG', 'chem. Zinn', 'chem. Silber', 'OSP'], 'HAL bleifrei'),
        ('loetstopp', 'Lötstopplack (Farbe)', ['grün', 'schwarz', 'blau', 'rot', 'lila', 'weiß', 'gelb'], 'grün'),
        ('bestueckungsdruck', 'Bestückungsdruck (Farbe)', ['weiß', 'schwarz', 'kein'], 'weiß'),
        ('via_fuellung', 'Via-Füllung', ['keine (offen)',
                                         'abgedeckt (tented)',
                                         'verschlossen (plugged, IPC-4761 Typ III)',
                                         'gefüllt (IPC-4761 Typ VI)',
                                         'gefüllt und abgedeckelt (IPC-4761 Typ VII)'], 'keine (offen)'),
    ]),
    ('MECHANISCHE BEARBEITUNG', [
        ('kontur', 'Konturbearbeitung', ['gefräst', 'geritzt (V-Cut, gebrochen)', 'gefräst und geritzt'], 'gefräst'),
    ]),
]

# header fields that can be edited in the dialog (the others come from the release / board)
HEADER_FIELDS = [
    ('projekt', 'Projekt'),
    ('firma', 'Firma'),
    ('freigegeben_von', 'Freigegeben von'),
]

AUTO_KEYS = [key for _, fields in SECTIONS for key, _, choices, _ in fields if choices is AUTO]

# can be defined in Board Setup -> Physical Stackup; if so, the stackup is the source (read only in the dialog)
STACKUP_KEYS = ['basismaterial', 'kupferdicke', 'oberflaeche', 'loetstopp', 'bestueckungsdruck']

# always taken from the board when the dialog opens (not from the stored values)
BOARD_KEYS = AUTO_KEYS + ['dicke']


def defaults():
    values = {key: default for _, fields in SECTIONS for key, _, _, default in fields}
    values.update({key: '' for key, _ in HEADER_FIELDS})
    values['firma'] = 'Schienle'
    values['bemerkungen'] = ''
    return values


def build_sections(values):
    '''[(title, [(label, value), ...]), ...] for the PDF'''
    return [(title, [(label, values.get(key, '')) for key, label, _, _ in fields]) for title, fields in SECTIONS]


def board_values(board):
    '''Values read from the board: layer count, outline size, thickness, project title, company.'''
    values = {}

    try:
        values['lagenanzahl'] = str(board.copper_layer_count())
    except Exception:
        pass
    try:
        size = board.board_edges_size()
        if size:
            values['abmessungen'] = '{} x {}'.format(format_mm(size[0] / 1e6), format_mm(size[1] / 1e6))
    except Exception:
        pass
    try:
        values['dicke'] = format_mm(board.board_thickness() / 1e6)
    except Exception:
        pass

    title_block = board.title_block()
    title = board.expand_text_variables(title_block.title)
    company = board.expand_text_variables(title_block.company)
    values['projekt'] = title or os.path.splitext(os.path.basename(board.file_path))[0]
    if company:
        values['firma'] = company

    return values


def format_mm(value):
    return ('%.2f' % value).rstrip('0').rstrip('.')
