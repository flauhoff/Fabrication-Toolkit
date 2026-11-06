'''
Minimal, dependency free PDF writer (KiCad's Python has no reportlab) and the layout of the
"Leiterplattenspezifikation" (PCB specification) sheet.
'''
import os
import zlib

from .helvetica_metrics import HELVETICA, HELVETICA_BOLD
from .pngimage import read_png, crop_transparent, crop_transparent_offset
from .projection import page_matrix

PAGE_WIDTH, PAGE_HEIGHT = 595.28, 841.89   # A4 in pt

FONTS = {'regular': ('F1', 'Helvetica', HELVETICA), 'bold': ('F2', 'Helvetica-Bold', HELVETICA_BOLD)}

RED = (0.906, 0.196, 0.220)
BLACK = (0.0, 0.0, 0.0)
DARK = (0.12, 0.12, 0.12)
GREY = (0.40, 0.40, 0.40)
LIGHT_GREY = (0.45, 0.45, 0.45)
CELL = (0.949, 0.949, 0.949)
RULE = (0.80, 0.80, 0.80)
WHITE = (1.0, 1.0, 1.0)


def _encode(text):
    data = str(text).encode('cp1252', errors='replace')
    return data.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def text_width(text, font='regular', size=10):
    widths = FONTS[font][2]
    total = 0
    for b in str(text).encode('cp1252', errors='replace'):
        total += widths[b - 32] if b >= 32 else 0
    return total * size / 1000.0


def wrap_text(text, width, font='regular', size=10):
    '''Word wrap to the given width; explicit line breaks are kept.'''
    lines = []
    for paragraph in str(text).splitlines() or ['']:
        line = ''
        for word in paragraph.split(' '):
            candidate = word if not line else line + ' ' + word
            if line and text_width(candidate, font, size) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def _jpeg_size(data):
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], 'big')
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], 'big'), int.from_bytes(data[i + 5:i + 7], 'big')
        i += 2 + length
    raise ValueError('Not a JPEG file')


class PdfCanvas:
    '''Multi page canvas. All y coordinates are measured from the TOP of the page.'''

    def __init__(self):
        self.pages = [[]]
        self.images = []

    @property
    def ops(self):
        return self.pages[-1]

    def new_page(self):
        self.pages.append([])

    @staticmethod
    def _n(value):
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def _y(self, y):
        return PAGE_HEIGHT - y

    def rect(self, x, y, w, h, color):
        n = self._n
        self.ops.append('%s %s %s rg %s %s %s %s re f' % (n(color[0]), n(color[1]), n(color[2]), n(x), n(self._y(y + h)), n(w), n(h)))

    def line(self, x1, y, x2, width=0.5, color=BLACK):
        n = self._n
        self.ops.append('%s %s %s RG %s w %s %s m %s %s l S' % (n(color[0]), n(color[1]), n(color[2]), n(width), n(x1), n(self._y(y)), n(x2), n(self._y(y))))

    def text(self, x, y, text, font='regular', size=10, color=BLACK, align='left'):
        '''y is the baseline'''
        if align != 'left':
            w = text_width(text, font, size)
            x -= w if align == 'right' else w / 2
        n = self._n
        self.ops.append(b'BT /%s %s Tf %s %s %s rg %s %s Td (%s) Tj ET' % (
            FONTS[font][0].encode(), n(size).encode(), n(color[0]).encode(), n(color[1]).encode(), n(color[2]).encode(),
            n(x).encode(), n(self._y(y)).encode(), _encode(text)))

    def jpeg(self, path, x, y, w):
        with open(path, 'rb') as f:
            data = f.read()
        pw, ph = _jpeg_size(data)
        h = w * ph / pw
        name = 'Im%d' % (len(self.images) + 1)
        self.images.append((name, b'/Filter /DCTDecode', data, pw, ph, None))
        n = self._n
        self.ops.append('q %s 0 0 %s %s %s cm /%s Do Q' % (n(w), n(h), n(x), n(self._y(y + h)), name))
        return h

    def add_png(self, path):
        '''Adds a PNG (transparent border cropped) as image resource.
        Returns (name, cropped width, cropped height, crop left, crop top, full width, full height).'''
        width, height, rgb, alpha = read_png(path)
        pw, ph, rgb, alpha, crop_left, crop_top = crop_transparent_offset(width, height, rgb, alpha)
        name = 'Im%d' % (len(self.images) + 1)
        smask = zlib.compress(alpha) if alpha is not None else None
        self.images.append((name, b'/Filter /FlateDecode', zlib.compress(rgb), pw, ph, smask))
        return name, pw, ph, crop_left, crop_top, width, height

    def draw_image(self, name, matrix):
        '''Draws an image resource with the given PDF transformation matrix (a, b, c, d, e, f; page y up).'''
        self.ops.append('q %s cm /%s Do Q' % (' '.join(self._n(v) for v in matrix), name))

    def png(self, path, x, y, max_w, max_h):
        '''Places a PNG (transparent border cropped) centered in the given box. Returns the used height.'''
        pw, ph, rgb, alpha = crop_transparent(*read_png(path))
        scale = min(max_w / pw, max_h / ph)
        w, h = pw * scale, ph * scale
        name = 'Im%d' % (len(self.images) + 1)
        smask = zlib.compress(alpha) if alpha is not None else None
        self.images.append((name, b'/Filter /FlateDecode', zlib.compress(rgb), pw, ph, smask))
        n = self._n
        self.ops.append('q %s 0 0 %s %s %s cm /%s Do Q' % (n(w), n(h), n(x + (max_w - w) / 2), n(self._y(y + h)), name))
        return h

    def save(self, path):
        objects = []

        def add(body):
            objects.append(body)
            return len(objects)

        catalog = add(None)
        pages = add(None)
        fonts = {key: add(b'<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>' % base.encode())
                 for key, base, _ in FONTS.values()}
        images = {}
        for name, filt, data, pw, ph, smask in self.images:
            mask = b''
            if smask is not None:
                mask_obj = add(b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray '
                               b'/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream' % (pw, ph, len(smask), smask))
                mask = b' /SMask %d 0 R' % mask_obj
            images[name] = add(b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB '
                               b'/BitsPerComponent 8 %s%s /Length %d >>\nstream\n%s\nendstream' % (pw, ph, filt, mask, len(data), data))
        resources = b'<< /Font << %s >> /XObject << %s >> >>' % (
            b' '.join(b'/%s %d 0 R' % (k.encode(), v) for k, v in fonts.items()),
            b' '.join(b'/%s %d 0 R' % (k.encode(), v) for k, v in images.items()))
        kids = []
        for ops in self.pages:
            content = zlib.compress(b'\n'.join(op if isinstance(op, bytes) else op.encode('latin-1') for op in ops))
            stream = add(b'<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream' % (len(content), content))
            kids.append(add(b'<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %s %s] /Resources %s /Contents %d 0 R >>' % (
                pages, self._n(PAGE_WIDTH).encode(), self._n(PAGE_HEIGHT).encode(), resources, stream)))
        objects[catalog - 1] = b'<< /Type /Catalog /Pages %d 0 R >>' % pages
        objects[pages - 1] = b'<< /Type /Pages /Kids [%s] /Count %d >>' % (b' '.join(b'%d 0 R' % k for k in kids), len(kids))

        out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = []
        for number, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += b'%d 0 obj\n%s\nendobj\n' % (number, body)
        xref = len(out)
        out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
        out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
        out += b'trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, catalog, xref)

        with open(path, 'wb') as f:
            f.write(out)


def _page_head(c, header, logo, left, right):
    if logo and os.path.isfile(logo):
        c.jpeg(logo, left, 40, 143)
    c.text(right, 62, 'Leiterplattenspezifikation', 'bold', 16, BLACK, 'right')
    c.text(right, 77, header.get('projekt', ''), 'regular', 9, GREY, 'right')
    c.line(left, 99, right, 2, RED)


def _page_foot(c, left, right, page, count):
    c.line(left, 789, right, 0.5, RULE)
    c.text(left, 799, 'Bei Abweichungen zwischen Fertigungsdaten und Spezifikation bitte Rücksprache halten.', 'regular', 7, GREY)
    c.text(right, 799, 'Seite {} von {}'.format(page, count) if count > 1 else 'Seite 1', 'regular', 7, GREY, 'right')


def _three_views(c, views, left, right, top, bottom):
    '''
    Draws the views (see projection.py) below each other, same scale, aligned on the board center.
    views: [(caption, png file, 2x2 page matrix), ...]
    '''
    label_height, gap = 14, 16
    items = []
    for caption, png, ((a, b), (cc, d)) in views:
        name, cw, ch, crop_left, crop_top, width, height = c.add_png(png)
        # board center = image center of the render (y up, relative to the cropped image)
        center = (width / 2.0 - crop_left, ch - (height / 2.0 - crop_top))
        corners = [(x * a + y * cc, x * b + y * d) for x in (0, cw) for y in (0, ch)]
        min_x, min_y = min(p[0] for p in corners), min(p[1] for p in corners)
        tw, th = max(p[0] for p in corners) - min_x, max(p[1] for p in corners) - min_y
        cx = center[0] * a + center[1] * cc - min_x
        items.append((caption, name, cw, ch, (a, b, cc, d), min_x, min_y, tw, th, cx))

    half_width = max(max(cx, tw - cx) for _, _, _, _, _, _, _, tw, _, cx in items)
    scale = min((right - left) / (2.0 * half_width),
                (bottom - top - len(items) * (label_height + gap)) / sum(item[8] for item in items))

    middle = (left + right) / 2.0
    y = top
    for caption, name, cw, ch, (a, b, cc, d), min_x, min_y, tw, th, cx in items:
        c.text(left, y + 9, caption, 'bold', 8, GREY)
        y += label_height
        origin_x = middle - cx * scale
        origin_y = PAGE_HEIGHT - (y + th * scale)
        c.draw_image(name, (scale * cw * a, scale * cw * b, scale * ch * cc, scale * ch * d,
                            origin_x - scale * min_x, origin_y - scale * min_y))
        y += th * scale + gap


def write_spec_pdf(path, header, sections, remarks, logo=None, views=None):
    '''
    header:   dict with projekt, leiterplatte, firma, freigabedatum, freigegeben_von, zeichnungsnummer, index
    sections: [(title, [(label, value), ...]), ...]
    remarks:  free text
    views:    optional three-view drawing [(caption, png file, 2x2 page matrix), ...] shown on page 2
    '''
    c = PdfCanvas()
    left, right = 50, 545
    views = [view for view in (views or []) if view[1] and os.path.isfile(view[1])]
    count = 2 if views else 1

    _page_head(c, header, logo, left, right)

    # header block with index box; long values (e.g. company) wrap to max. 2 lines per field
    top, split = 120, 436
    columns = ((left + 11, 255 - (left + 11) - 10), (255, split - 255 - 10))
    fields = [('PROJEKT', 'projekt', 'FREIGABEDATUM', 'freigabedatum'),
              ('LEITERPLATTE', 'leiterplatte', 'FREIGEGEBEN VON', 'freigegeben_von'),
              ('FIRMA', 'firma', 'ZEICHNUNGSNUMMER', 'zeichnungsnummer')]
    layout, y = [], top + 20
    for l1, k1, l2, k2 in fields:
        cells = []
        for (x, width), label, key in zip(columns, (l1, l2), (k1, k2)):
            lines = wrap_text(header.get(key, ''), width, 'bold', 10)
            if len(lines) > 2:
                lines = lines[:1] + [lines[1] + ' ...']
            cells.append((x, label, lines))
        layout.append((y, cells))
        y += 17 + 11 * max(len(lines) for _, _, lines in cells)
    height = max(96, y - top - 3)

    c.rect(left, top, split - left, height, CELL)
    c.rect(split, top, right - split, height, DARK)
    c.text((split + right) / 2, top + height / 2 - 18, 'INDEX', 'regular', 8.5, WHITE, 'center')
    c.text((split + right) / 2, top + height / 2 + 18, header.get('index', ''), 'bold', 26, WHITE, 'center')
    for y, cells in layout:
        for x, label, lines in cells:
            c.text(x, y, label, 'regular', 6.5, LIGHT_GREY)
            for i, line in enumerate(lines):
                c.text(x, y + 10 + 11 * i, line, 'bold', 10, BLACK)

    # tables
    y = top + height + 22
    for title, rows in sections:
        c.text(left, y, title, 'bold', 9, RED)
        y += 11
        c.line(left, y, right, 0.8, BLACK)
        for label, value in rows:
            # long values (e.g. marking) wrap; the row grows by 11 pt per additional line
            lines = wrap_text(value, right - left - 203, 'bold', 9)
            row_height = 25 + 11 * (len(lines) - 1)
            c.rect(left, y, 185, row_height, CELL)
            c.text(left + 8, y + 16, label, 'regular', 9, GREY)
            for i, line in enumerate(lines):
                c.text(left + 195, y + 16 + 11 * i, line, 'bold', 9, BLACK)
            y += row_height
            c.line(left, y, right, 0.5, RULE)
        y += 18

    # remarks
    c.text(left, y, 'BEMERKUNGEN', 'bold', 9, RED)
    y += 11
    c.line(left, y, right, 0.8, BLACK)
    y += 3
    lines = wrap_text(remarks or '-', right - left - 16, 'regular', 9)
    max_lines = int((770 - y) / 12.5)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [lines[max_lines - 1] + ' ...']
    for line in lines:
        y += 12.5
        c.text(left + 8, y, line, 'regular', 9, BLACK)
    y += 8
    c.line(left, y, right, 0.5, RULE)

    _page_foot(c, left, right, 1, count)

    # page 2: board views
    if views:
        c.new_page()
        _page_head(c, header, logo, left, right)
        c.text(left, 122, 'ANSICHTEN', 'bold', 9, RED)
        c.text(right, 122, 'Projektionsmethode 1 (ISO 128, europäisch)', 'regular', 7, GREY, 'right')
        c.line(left, 133, right, 0.8, BLACK)
        _three_views(c, views, left, right, 145, 775)
        _page_foot(c, left, right, 2, count)

    c.save(path)
    return path
