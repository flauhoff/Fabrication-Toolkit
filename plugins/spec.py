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
    ('material',       'Basismaterial',                    ['FR4', 'FR4 High-Tg (Tg 170)', 'Aluminium (IMS)', 'Polyimid (flexibel)'], 'FR4', True),
    ('layers',         'Lagenanzahl',                      'board', '', True),
    ('dimensions',     'Abmessungen [mm]',                 'board', '', True),
    ('thickness',      'Leiterplattendicke [mm]',          ['0.8', '1.0', '1.2', '1.6', '2.0', '2.4'], 'board', True),
    ('copper_outer',   'Kupferdicke Außenlagen',           ['18 µm', '35 µm', '70 µm', '105 µm'], '35 µm', True),
    ('copper_inner',   'Kupferdicke Innenlagen',           ['-', '18 µm', '35 µm', '70 µm'], '-', False),
    ('surface',        'Oberfläche',                       ['HAL bleifrei', 'ENIG (chem. Ni/Au)', 'OSP', 'chem. Zinn', 'chem. Silber'], 'HAL bleifrei', True),
    ('soldermask',     'Lötstopplack',                     ['grün', 'schwarz', 'blau', 'rot', 'weiß', 'ohne'], 'grün', True),
    ('silkscreen',     'Bestückungsdruck',                 ['weiß', 'schwarz', 'gelb', 'ohne'], 'weiß', True),
    ('min_track',      'Min. Leiterbahnbreite [mm]',       'board', '', False),
    ('min_clearance',  'Min. Abstand (Designregel) [mm]',  'board', '', False),
    ('min_drill',      'Min. Bohrdurchmesser [mm]',        'board', '', False),
    ('ipc_class',      'Qualität (IPC-A-600)',             ['Klasse 2', 'Klasse 3'], 'Klasse 2', True),
    ('etest',          'Elektrischer Test',                ['ja', 'nein'], 'ja', True),
    ('impedance',      'Impedanzkontrolle',                ['nein', 'ja (siehe Bemerkungen)'], 'nein', True),
    ('delivery',       'Liefereinheit',                    ['Einzelkarte', 'Nutzen (gemäß Gerber)', 'Nutzen durch Hersteller'], 'Einzelkarte', True),
    ('quantity',       'Menge',                            None, '', False),
    ('author',         'Erstellt / freigegeben von',       None, '', True),
    ('notes',          'Bemerkungen',                      None, '', False),
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

    min_track = None
    min_drill = None
    try:
        for track in board.GetTracks():
            if 'VIA' in track.GetClass().upper():
                drill = track.GetDrillValue()
                if drill > 0:
                    min_drill = drill if min_drill is None else min(min_drill, drill)
            else:
                width = track.GetWidth()
                if width > 0:
                    min_track = width if min_track is None else min(min_track, width)
    except Exception:
        pass

    try:
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                size = pad.GetDrillSize()
                drill = min(size.x, size.y)
                if drill > 0:
                    min_drill = drill if min_drill is None else min(min_drill, drill)
    except Exception:
        pass

    if min_track is not None:
        values['min_track'] = _mm(min_track)
    if min_drill is not None:
        values['min_drill'] = _mm(min_drill)

    clearance = _get_default_clearance(board)
    if clearance:
        values['min_clearance'] = _mm(clearance)

    return values


def _get_default_clearance(board):
    '''Smallest clearance of the design rules (minimum clearance or default net class).'''
    settings = board.GetDesignSettings()
    candidates = []

    getters = [
        lambda: settings.m_MinClearance,
        lambda: settings.m_NetSettings.GetDefaultNetclass().GetClearance(),   # KiCad 8+
        lambda: settings.m_NetSettings.m_DefaultNetClass.GetClearance(),      # KiCad 7
        lambda: settings.GetDefault().GetClearance(),                         # KiCad 6
    ]
    for getter in getters:
        try:
            value = int(getter())
            if value > 0:
                candidates.append(value)
        except Exception:
            pass

    return min(candidates) if candidates else None


def default_spec(board):
    '''Specification with the defaults, board based values filled in.'''
    board_values = read_board_values(board)
    spec = {}
    for key, _, _, default, _ in FIELDS:
        spec[key] = board_values.get(key, '') if default == 'board' else default

    if board_values.get('layers') and int(board_values['layers']) > 2:
        spec['copper_inner'] = '35 µm'

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
