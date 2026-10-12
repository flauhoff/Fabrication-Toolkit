import os
import json
import datetime

import pcbnew  # type: ignore

from .pdf import Document, wrap_text

specFileName = 'leiterplattenspezifikation.json'
specOutputName = 'Leiterplattenspezifikation'
logoFile = os.path.join(os.path.dirname(__file__), 'schienle-logo.png')

# Field definitions: (key, label, choices, default, required)
# - choices: list -> editable drop down, None -> free text, 'board' -> read from the board (read only)
# - default 'board' -> prefilled from the board, but editable
FIELDS = [
    ('material',       'Basismaterial',               ['FR4', 'Flex', 'Aluminium', 'Kupferkern'], 'FR4', True),
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

# Grouping of the fields in the PDF
SECTIONS = [
    ('Allgemein',              ['material', 'layers', 'dimensions', 'quantity', 'product_type', 'designs', 'delivery']),
    ('Leiterplatte',           ['thickness', 'material_type', 'surface', 'soldermask', 'silkscreen']),
    ('Mechanische Bearbeitung', ['contour']),
    ('Bemerkungen',            ['notes']),
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

    return {
        'title': title or board_name,
        'file': os.path.basename(board.GetFileName()),
        'index': index or title_block.GetRevision() or '-',
        'company': company or '-',
        'date': datetime.datetime.now().strftime('%d.%m.%Y'),
    }


# PDF layout (points)
_RED = (231, 50, 56)
_DARK = (28, 28, 26)
_GREY = (110, 110, 110)
_LINE = (205, 205, 205)
_SHADE = (243, 243, 243)
_MARGIN = 50
_LABEL_WIDTH = 185
_ROW_PADDING = 6
_FONT_SIZE = 10
_LINE_HEIGHT = 13


def render_pdf(board, spec, index, path):
    labels = {key: label for key, label, _, _, _ in FIELDS}
    header = _header(board, index)

    doc = Document()
    left, right = _MARGIN, doc.width - _MARGIN
    width = right - left

    def page_header():
        doc.image(logoFile, left, 40, w=150)
        doc.text(right, 62, 'Leiterplattenspezifikation', 'Helvetica-Bold', 18, _DARK, align='right')
        doc.text(right, 78, header['title'], 'Helvetica', 10, _GREY, align='right')
        doc.rect(left, 98, width, 2.5, fill=_RED)
        return 120

    def page_footer():
        y = doc.height - 40
        doc.line(left, y - 12, right, y - 12, _LINE)
        doc.text(left, y, 'Bei Abweichungen zwischen Fertigungsdaten und Spezifikation bitte Rücksprache halten.', 'Helvetica', 8, _GREY)
        doc.text(right, y, 'Seite {}'.format(len(doc.pages)), 'Helvetica', 8, _GREY, align='right')

    y = page_header()

    # Release data box: index highlighted on the right
    box_height = 92
    doc.rect(left, y, width, box_height, fill=_SHADE)
    doc.rect(right - 110, y, 110, box_height, fill=_DARK)
    doc.text(right - 55, y + 30, 'INDEX', 'Helvetica', 9, (255, 255, 255), align='center')
    doc.text(right - 55, y + 66, header['index'], 'Helvetica-Bold', 26, (255, 255, 255), align='center')

    info = [('Projekt', header['title']), ('Leiterplatte', header['file']),
            ('Firma', header['company']), ('Freigabedatum', header['date']),
            ('Freigegeben von', (spec.get('author') or '').strip() or '-')]
    columns = [info[:3], info[3:]]
    column_width = (width - 110) / 2
    for column, rows in enumerate(columns):
        x = left + 12 + column * column_width
        for row, (label, value) in enumerate(rows):
            ry = y + 22 + row * 26
            doc.text(x, ry, label.upper(), 'Helvetica', 7, _GREY)
            value = wrap_text(value, 'Helvetica-Bold', 10, column_width - 20)[0]
            doc.text(x, ry + 10, value, 'Helvetica-Bold', 10, _DARK)
    y += box_height + 26

    value_x = left + _LABEL_WIDTH + 10
    value_width = right - value_x - 8

    for title, keys in SECTIONS:
        rows = [(labels[k], (spec.get(k) or '').strip() or '-') for k in keys]
        if title == 'Bemerkungen' and rows[0][1] == '-':
            continue

        if y + 50 > doc.height - 70:
            page_footer()
            doc.new_page()
            y = page_header()

        doc.text(left, y, title.upper(), 'Helvetica-Bold', 10, _RED)
        y += 7

        bottom = doc.height - 70
        for number, (label, value) in enumerate(rows):
            is_text = title == 'Bemerkungen'
            lines = wrap_text(value, 'Helvetica', _FONT_SIZE, width - 16) if is_text else \
                wrap_text(value, 'Helvetica-Bold', _FONT_SIZE, value_width)

            # Long values (notes) are continued on the next page
            while lines:
                fitting = int((bottom - y - 2 * _ROW_PADDING) // _LINE_HEIGHT)
                if fitting < min(len(lines), 3):
                    page_footer()
                    doc.new_page()
                    y = page_header()
                    continue

                chunk, lines = lines[:fitting], lines[fitting:]
                row_height = len(chunk) * _LINE_HEIGHT + 2 * _ROW_PADDING

                if not is_text:
                    doc.rect(left, y, _LABEL_WIDTH, row_height, fill=_SHADE)
                doc.line(left, y + row_height, right, y + row_height, _LINE)
                if number == 0:
                    doc.line(left, y, right, y, _DARK, 1)

                text_y = y + _ROW_PADDING + _FONT_SIZE
                if not is_text:
                    doc.text(left + 8, text_y, label, 'Helvetica', _FONT_SIZE, _GREY)
                for line in chunk:
                    if is_text:
                        doc.text(left + 8, text_y, line, 'Helvetica', _FONT_SIZE, _DARK)
                    else:
                        doc.text(value_x, text_y, line, 'Helvetica-Bold', _FONT_SIZE, _DARK)
                    text_y += _LINE_HEIGHT
                y += row_height

        y += 22

    page_footer()
    doc.save(path)
    return path


def write_spec_files(board, spec, index, directories):
    '''Writes the specification as PDF into each of the given directories.'''
    for directory in directories:
        render_pdf(board, spec, index, os.path.join(directory, specOutputName + '.pdf'))
