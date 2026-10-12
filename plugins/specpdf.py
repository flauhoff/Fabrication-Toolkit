'''
Minimal, dependency free PDF writer (KiCad's Python has no reportlab) and the layout of the
"Leiterplattenspezifikation" (PCB specification) sheet.
'''
import os
import zlib

from .helvetica_metrics import HELVETICA, HELVETICA_BOLD

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
    '''Single page canvas. All y coordinates are measured from the TOP of the page.'''

    def __init__(self):
        self.ops = []
        self.images = []

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
        self.images.append((name, data, pw, ph))
        n = self._n
        self.ops.append('q %s 0 0 %s %s %s cm /%s Do Q' % (n(w), n(h), n(x), n(self._y(y + h)), name))
        return h

    def save(self, path):
        content = b'\n'.join(op if isinstance(op, bytes) else op.encode('latin-1') for op in self.ops)
        content = zlib.compress(content)

        objects = []

        def add(body):
            objects.append(body)
            return len(objects)

        catalog = add(None)
        pages = add(None)
        fonts = {key: add(b'<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>' % base.encode())
                 for key, base, _ in FONTS.values()}
        images = {}
        for name, data, pw, ph in self.images:
            images[name] = add(b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB '
                               b'/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n%s\nendstream' % (pw, ph, len(data), data))
        stream = add(b'<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream' % (len(content), content))
        resources = b'<< /Font << %s >> /XObject << %s >> >>' % (
            b' '.join(b'/%s %d 0 R' % (k.encode(), v) for k, v in fonts.items()),
            b' '.join(b'/%s %d 0 R' % (k.encode(), v) for k, v in images.items()))
        page = add(b'<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %s %s] /Resources %s /Contents %d 0 R >>' % (
            pages, self._n(PAGE_WIDTH).encode(), self._n(PAGE_HEIGHT).encode(), resources, stream))
        objects[catalog - 1] = b'<< /Type /Catalog /Pages %d 0 R >>' % pages
        objects[pages - 1] = b'<< /Type /Pages /Kids [%d 0 R] /Count 1 >>' % page

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


def write_spec_pdf(path, header, sections, remarks, logo=None):
    '''
    header:   dict with projekt, leiterplatte, firma, freigabedatum, freigegeben_von, zeichnungsnummer, index
    sections: [(title, [(label, value), ...]), ...]
    remarks:  free text
    '''
    c = PdfCanvas()
    left, right = 50, 545

    # title
    if logo and os.path.isfile(logo):
        c.jpeg(logo, left, 40, 143)
    c.text(right, 62, 'Leiterplattenspezifikation', 'bold', 16, BLACK, 'right')
    c.text(right, 77, header.get('projekt', ''), 'regular', 9, GREY, 'right')
    c.line(left, 99, right, 2, RED)

    # header block with index box
    top, height, split = 120, 96, 436
    c.rect(left, top, split - left, height, CELL)
    c.rect(split, top, right - split, height, DARK)
    c.text((split + right) / 2, top + 30, 'INDEX', 'regular', 8.5, WHITE, 'center')
    c.text((split + right) / 2, top + 66, header.get('index', ''), 'bold', 26, WHITE, 'center')
    fields = [('PROJEKT', 'projekt', 'FREIGABEDATUM', 'freigabedatum'),
              ('LEITERPLATTE', 'leiterplatte', 'FREIGEGEBEN VON', 'freigegeben_von'),
              ('FIRMA', 'firma', 'ZEICHNUNGSNUMMER', 'zeichnungsnummer')]
    for row, (l1, k1, l2, k2) in enumerate(fields):
        y = top + 20 + row * 27
        for x, label, key in ((left + 11, l1, k1), (255, l2, k2)):
            c.text(x, y, label, 'regular', 6.5, LIGHT_GREY)
            c.text(x, y + 10, header.get(key, ''), 'bold', 10, BLACK)

    # tables
    y = top + height + 22
    for title, rows in sections:
        c.text(left, y, title, 'bold', 9, RED)
        y += 11
        c.line(left, y, right, 0.8, BLACK)
        for label, value in rows:
            c.rect(left, y, 185, 25, CELL)
            c.text(left + 8, y + 16, label, 'regular', 9, GREY)
            c.text(left + 195, y + 16, value, 'bold', 9, BLACK)
            y += 25
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

    # footer
    c.line(left, 789, right, 0.5, RULE)
    c.text(left, 799, 'Bei Abweichungen zwischen Fertigungsdaten und Spezifikation bitte Rücksprache halten.', 'regular', 7, GREY)
    c.text(right, 799, 'Seite 1', 'regular', 7, GREY, 'right')

    c.save(path)
    return path
