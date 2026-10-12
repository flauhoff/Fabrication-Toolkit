'''
Reads release relevant information directly from the saved KiCad files (no pcbnew needed):
- the physical stackup (Board Setup -> Physical Stackup) of the .kicad_pcb
- the title block revision of the root .kicad_sch
'''
import re

# KiCad names (board_stackup_manager/stackup_predefined_prms.cpp) -> specification wording
FINISHES = {
    'None': 'keine',
    'HAL SnPb': 'HAL verbleit',
    'HAL lead-free': 'HAL bleifrei',
    'ENIG': 'chem. Gold (ENIG)',
    'ENEPIG': 'ENEPIG',
    'Hard gold': 'Hartgold',
    'Immersion tin': 'chem. Zinn',
    'Immersion nickel': 'chem. Nickel',
    'Immersion silver': 'chem. Silber',
    'Immersion gold': 'chem. Gold',
    'HT_OSP': 'OSP (Hochtemperatur)',
    'OSP': 'OSP',
}

COLORS = {
    'Green': 'grün',
    'Red': 'rot',
    'Blue': 'blau',
    'Purple': 'lila',
    'Black': 'schwarz',
    'White': 'weiß',
    'Yellow': 'gelb',
}

MATERIALS = {
    'FR4': 'FR4',
    'Polyimide': 'Polyimid',
    'PTFE': 'PTFE',
    'Aluminum': 'Aluminium',
}

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def _parse(text, start):
    '''Parses one s-expression starting at text[start] == "(" into nested lists.'''
    stack, current = [], None
    for match in _TOKEN.finditer(text, start):
        token = match.group(0)
        if token == '(':
            new = []
            if current is not None:
                current.append(new)
                stack.append(current)
            current = new
        elif token == ')':
            if not stack:
                return current
            current = stack.pop()
        else:
            if token.startswith('"'):
                token = token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            current.append(token)
    return current


def _find(text, head):
    '''First "(head ..." s-expression in text, or None.'''
    match = re.search(r'\(' + re.escape(head) + r'[\s)]', text)
    return _parse(text, match.start()) if match else None


def _value(node, key):
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == key and len(child) > 1:
            return child[1]
    return None


def _join(top, bottom):
    if top == bottom or not bottom:
        return top
    if not top:
        return bottom
    return '{} (oben) / {} (unten)'.format(top, bottom)


def _translate(value, table):
    if not value or value == 'User defined':
        return None
    return table.get(value, value)


def read_stackup(board_file):
    '''
    Specification values from the physical stackup of the saved board, e.g.
    {'kupferdicke': '35', 'oberflaeche': 'HAL bleifrei', 'loetstopp': 'grün', 'bestueckungsdruck': 'weiß', 'basismaterial': 'FR4'}.
    Only values that are defined in the stackup are returned.
    '''
    with open(board_file, 'r', encoding='utf-8') as f:
        text = f.read()

    stackup = _find(text, 'stackup')
    if not stackup:
        return {}

    values = {}
    layers = {}
    copper, materials = [], []
    for child in stackup[1:]:
        if not isinstance(child, list) or not child:
            continue
        if child[0] == 'layer':
            name, kind = child[1], (_value(child, 'type') or '').lower()
            layers[name] = child
            if kind == 'copper':
                thickness = _value(child, 'thickness')
                if thickness:
                    copper.append((name, round(float(thickness) * 1000)))
            elif kind in ('core', 'prepreg') or name.startswith('dielectric'):
                material = _translate(_value(child, 'material'), MATERIALS)
                if material and material not in materials:
                    materials.append(material)
        elif child[0] == 'copper_finish':
            finish = _translate(child[1], FINISHES)
            if finish:
                values['oberflaeche'] = finish

    if copper:
        outer = sorted({um for name, um in copper if name in ('F.Cu', 'B.Cu')})
        inner = sorted({um for name, um in copper if name not in ('F.Cu', 'B.Cu')})
        text_outer = ' / '.join(str(um) for um in outer)
        if inner and inner != outer:
            values['kupferdicke'] = '{} (außen), {} (innen)'.format(text_outer, ' / '.join(str(um) for um in inner))
        else:
            values['kupferdicke'] = text_outer

    for key, top, bottom in (('loetstopp', 'F.Mask', 'B.Mask'), ('bestueckungsdruck', 'F.SilkS', 'B.SilkS')):
        top_color = _translate(_value(layers[top], 'color'), COLORS) if top in layers else None
        bottom_color = _translate(_value(layers[bottom], 'color'), COLORS) if bottom in layers else None
        color = _join(top_color, bottom_color)
        if color:
            values[key] = color

    if materials:
        values['basismaterial'] = ' / '.join(materials)

    return values


def read_schematic_revision(schematic_file):
    '''Raw revision text of the root schematic title block ("" if not set), None if the file is missing.'''
    try:
        with open(schematic_file, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return None
    title_block = _find(text, 'title_block')
    if not title_block:
        return ''
    return _value(title_block, 'rev') or ''
