import os
import json
import html
import datetime

import pcbnew  # type: ignore

specFileName = 'leiterplattenspezifikation.json'
specOutputName = 'Leiterplattenspezifikation'

# Field definitions: (key, label, choices, default, required)
# - choices: list -> editable drop down, None -> free text, 'board' -> read from the board (read only)
# - default 'board' -> prefilled from the board, but editable
FIELDS = [
    ('material',       'Basismaterial',               ['FR4', 'Flex', 'Aluminium', 'Kupferkern', 'Rogers', 'PTFE (Teflon)', 'HDI'], 'FR4', True),
    ('layers',         'Lagenanzahl',                 'board', '', True),
    ('dimensions',     'Abmessungen [mm]',            'board', '', True),
    ('quantity',       'Menge',                       None, '', False),
    ('product_type',   'Produkttyp',                  ['Industrie-/Consumer-Elektronik', 'Luft- und Raumfahrt', 'Medizintechnik'], 'Industrie-/Consumer-Elektronik', True),
    ('designs',        'Anzahl verschiedener Designs', ['1', '2', '3', '4'], '1', True),
    ('delivery',       'Liefereinheit',               ['Einzelkarte', 'Nutzen durch Kunde (gemäß Gerber)', 'Nutzen durch Hersteller'], 'Einzelkarte', True),
    ('thickness',      'Leiterplattendicke [mm]',     ['0.4', '0.6', '0.8', '1.0', '1.2', '1.6', '2.0'], 'board', True),
    ('soldermask',     'Lötstopplack (Farbe)',        ['grün', 'violett', 'rot', 'gelb', 'blau', 'weiß', 'schwarz'], 'grün', True),
    ('silkscreen',     'Bestückungsdruck (Farbe)',    ['weiß', 'schwarz'], 'weiß', True),
    ('material_type',  'Materialtyp',                 ['FR4 TG135', 'KB6164 TG135', 'Nan Ya NP-140F', 'S1141 TG140', 'S1000H TG155'], 'FR4 TG135', True),
    ('surface',        'Oberfläche',                  ['OSP', 'HAL (bleihaltig)', 'HAL bleifrei', 'ENIG (chem. Ni/Au)'], 'HAL bleifrei', True),
    ('contour',        'Konturbearbeitung',           ['gefräst', 'geritzt (V-Cut, gebrochen)', 'gefräst mit Stegen (gebrochen)'], 'gefräst', True),
    ('author',         'Erstellt / freigegeben von',  None, '', True),
    ('notes',          'Bemerkungen',                 None, '', False),
]

BOARD_KEYS = [key for key, _, choices, _, _ in FIELDS if choices == 'board']


def get_spec_file_path(board_file):
    return os.path.join(os.path.dirname(os.path.abspath(board_file)), specFileName)


def spec_exists(board_file):
    return os.path.isfile(get_spec_file_path(board_file))


def _mm(value_nm):
    return '{:.3f}'.format(value_nm / 1e6).rstrip('0').rstrip('.')


def read_board_values(board):
    '''Reads the specification values that follow from the design itself.'''
    values = {}

    try:
        values['layers'] = str(board.GetCopperLayerCount())
    except Exception:
        pass

    try:
        values['thickness'] = _mm(board.GetDesignSettings().GetBoardThickness())
    except Exception:
        pass

    try:
        box = board.GetBoardEdgesBoundingBox()
        if box.GetWidth() > 0 and box.GetHeight() > 0:
            values['dimensions'] = '{} x {}'.format(_mm(box.GetWidth()), _mm(box.GetHeight()))
    except Exception:
        pass

    return values


def default_spec(board):
    '''Specification with the defaults, board based values filled in.'''
    board_values = read_board_values(board)
    spec = {}
    for key, _, _, default, _ in FIELDS:
        spec[key] = board_values.get(key, '') if default == 'board' else default

    return spec


def load_spec(board_file, board):
    '''Loads the stored specification of the project, completed by defaults and current board values.'''
    spec = default_spec(board)
    try:
        with open(get_spec_file_path(board_file), 'r', encoding='utf-8') as f:
            stored = json.load(f)
        spec.update({k: str(v) for k, v in stored.items() if k in spec})
    except (OSError, ValueError):
        pass

    # Values that follow from the design are always taken from the current board
    board_values = read_board_values(board)
    for key in BOARD_KEYS:
        spec[key] = board_values.get(key, '')

    return spec


def save_spec(board_file, spec):
    stored = {k: v for k, v in spec.items() if k not in BOARD_KEYS}
    with open(get_spec_file_path(board_file), 'w', encoding='utf-8') as f:
        json.dump(stored, f, indent=2, ensure_ascii=False)


def missing_fields(spec):
    '''Returns the labels of all required fields without value.'''
    return [label for key, label, choices, _, required in FIELDS
            if required and choices != 'board' and not (spec.get(key) or '').strip()]


def _header(board, index):
    title_block = board.GetTitleBlock()
    title = title_block.GetTitle()
    company = title_block.GetCompany()

    if hasattr(board, "GetProject") and hasattr(pcbnew, "ExpandTextVars"):
        project = board.GetProject()
        title = pcbnew.ExpandTextVars(title, project)
        company = pcbnew.ExpandTextVars(company, project)

    board_name = os.path.splitext(os.path.basename(board.GetFileName()))[0]

    return [
        ('Projekt', title or board_name),
        ('Leiterplatte (Datei)', os.path.basename(board.GetFileName())),
        ('Index', index or title_block.GetRevision() or '-'),
        ('Firma', company or '-'),
        ('Freigabedatum', datetime.datetime.now().strftime('%Y-%m-%d')),
    ]


def _rows(spec):
    return [(label, (spec.get(key) or '').strip() or '-') for key, label, _, _, _ in FIELDS]


def render_text(board, spec, index):
    header = _header(board, index)
    rows = _rows(spec)
    width = max(len(label) for label, _ in header + rows) + 2

    lines = ['LEITERPLATTENSPEZIFIKATION', '=' * 26, '']
    lines += ['{:<{w}}{}'.format(label + ':', value, w=width) for label, value in header]
    lines += ['', '-' * 60, '']
    for label, value in rows:
        value_lines = value.splitlines() or ['-']
        lines.append('{:<{w}}{}'.format(label + ':', value_lines[0], w=width))
        lines += [' ' * width + line for line in value_lines[1:]]
    lines += ['', 'Bei Abweichungen zwischen Fertigungsdaten und Spezifikation bitte Rücksprache halten.', '']

    return '\r\n'.join(lines)


def render_html(board, spec, index):
    def table(rows):
        return '\n'.join('<tr><th>{}</th><td>{}</td></tr>'.format(
            html.escape(label), html.escape(value).replace('\n', '<br>')) for label, value in rows)

    return '''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Leiterplattenspezifikation</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 2em; color: #000; }}
  h1 {{ font-size: 1.4em; border-bottom: 2px solid #000; padding-bottom: .3em; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 50em; margin-bottom: 1.5em; }}
  th, td {{ border: 1px solid #888; padding: .35em .6em; text-align: left; vertical-align: top; }}
  th {{ width: 40%; background: #eee; font-weight: normal; }}
  p {{ font-size: .9em; }}
</style>
</head>
<body>
<h1>Leiterplattenspezifikation</h1>
<table>
{}
</table>
<table>
{}
</table>
<p>Bei Abweichungen zwischen Fertigungsdaten und Spezifikation bitte R&uuml;cksprache halten.</p>
</body>
</html>
'''.format(table(_header(board, index)), table(_rows(spec)))


def write_spec_files(board, spec, index, text_dirs, html_dir):
    '''Writes the specification as text into each of `text_dirs` and as printable HTML into `html_dir`.'''
    text = render_text(board, spec, index)
    for directory in text_dirs:
        with open(os.path.join(directory, specOutputName + '.txt'), 'w', encoding='utf-8-sig', newline='') as f:
            f.write(text)

    with open(os.path.join(html_dir, specOutputName + '.html'), 'w', encoding='utf-8') as f:
        f.write(render_html(board, spec, index))
