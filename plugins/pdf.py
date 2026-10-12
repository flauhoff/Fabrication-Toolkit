'''
Minimal PDF writer (pure Python, no dependencies) for simple documents:
text in the standard Helvetica fonts, lines, rectangles and RGB PNG images.
Coordinates are in points (1/72 inch), origin top left.
'''
import struct
import zlib

A4 = (595.28, 841.89)

# Glyph widths of the standard fonts for the ASCII range 32..126 (1/1000 em)
_WIDTHS = {
    'Helvetica': [
        278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
        556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
        1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
        667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
        333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
        556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584],
    'Helvetica-Bold': [
        278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
        556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
        975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
        667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
        333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
        611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584],
}
_FONT_IDS = {'Helvetica': 'F1', 'Helvetica-Bold': 'F2'}


def text_width(text, font, size):
    widths = _WIDTHS[font]
    total = 0
    for char in text:
        code = ord(char)
        total += widths[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000.0


def wrap_text(text, font, size, max_width):
    '''Splits text into lines that fit into max_width (keeps explicit line breaks).'''
    lines = []
    for paragraph in (text or '').splitlines() or ['']:
        line = ''
        for word in paragraph.split(' '):
            candidate = word if not line else line + ' ' + word
            if line and text_width(candidate, font, size) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def _escape(text):
    data = text.encode('cp1252', errors='replace')
    return data.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def _color(rgb):
    return ' '.join('{:.3f}'.format(c / 255.0) for c in rgb).encode()


def _read_png(path):
    '''Reads an 8 bit RGB, non interlaced PNG. Its compressed data is embedded as is.'''
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Not a PNG file: ' + path)

    pos, idat, header = 8, b'', None
    while pos < len(data):
        length, chunk_type = struct.unpack('>I4s', data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if chunk_type == b'IHDR':
            header = struct.unpack('>IIBBBBB', chunk)
        elif chunk_type == b'IDAT':
            idat += chunk
        pos += 12 + length

    width, height, depth, color_type, _, _, interlace = header
    if depth != 8 or color_type != 2 or interlace != 0:
        raise ValueError('Only 8 bit RGB, non interlaced PNG images are supported: ' + path)
    return width, height, idat


class Document:
    def __init__(self, page_size=A4):
        self.width, self.height = page_size
        self.pages = []
        self.images = []
        self.new_page()

    def new_page(self):
        self.page = []
        self.pages.append(self.page)

    def _y(self, y):
        return self.height - y

    def rect(self, x, y, w, h, fill=None, stroke=None, line_width=0.5):
        ops = b''
        if fill:
            ops += _color(fill) + b' rg '
        if stroke:
            ops += _color(stroke) + b' RG ' + '{:.2f} w '.format(line_width).encode()
        ops += '{:.2f} {:.2f} {:.2f} {:.2f} re '.format(x, self._y(y + h), w, h).encode()
        ops += b'B' if fill and stroke else b'f' if fill else b'S'
        self.page.append(ops)

    def line(self, x1, y1, x2, y2, color=(0, 0, 0), line_width=0.5):
        self.page.append(_color(color) + ' RG {:.2f} w {:.2f} {:.2f} m {:.2f} {:.2f} l S'.format(
            line_width, x1, self._y(y1), x2, self._y(y2)).encode())

    def text(self, x, y, text, font='Helvetica', size=10, color=(0, 0, 0), align='left'):
        '''Draws a single line of text, y is the baseline.'''
        if align == 'right':
            x -= text_width(text, font, size)
        elif align == 'center':
            x -= text_width(text, font, size) / 2
        self.page.append(b'BT ' + _color(color) + ' rg /{} {:.2f} Tf {:.2f} {:.2f} Td ('.format(
            _FONT_IDS[font], size, x, self._y(y)).encode() + _escape(text) + b') Tj ET')

    def image(self, path, x, y, w=None, h=None):
        '''Draws a PNG image, keeping its aspect ratio if only w or h is given. Returns the drawn size.'''
        px_w, px_h, idat = _read_png(path)
        if w is None and h is None:
            w, h = px_w, px_h
        elif h is None:
            h = w * px_h / px_w
        elif w is None:
            w = h * px_w / px_h

        self.images.append((px_w, px_h, idat))
        name = 'Im{}'.format(len(self.images))
        self.page.append('q {:.2f} 0 0 {:.2f} {:.2f} {:.2f} cm /{} Do Q'.format(
            w, h, x, self._y(y + h), name).encode())
        return w, h

    def save(self, path):
        objects = []

        def add(obj):
            objects.append(obj)
            return len(objects)

        catalog = add(None)
        pages = add(None)
        fonts = {fid: add('<< /Type /Font /Subtype /Type1 /BaseFont /{} /Encoding /WinAnsiEncoding >>'.format(name).encode())
                 for name, fid in _FONT_IDS.items()}
        images = []
        for px_w, px_h, idat in self.images:
            images.append(add(('<< /Type /XObject /Subtype /Image /Width {0} /Height {1} /ColorSpace /DeviceRGB '
                               '/BitsPerComponent 8 /Filter /FlateDecode '
                               '/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {0} >> '
                               '/Length {2} >>\nstream\n').format(px_w, px_h, len(idat)).encode() + idat + b'\nendstream'))

        resources = '<< /Font << {} >> /XObject << {} >> >>'.format(
            ' '.join('/{} {} 0 R'.format(fid, num) for fid, num in fonts.items()),
            ' '.join('/Im{} {} 0 R'.format(i + 1, num) for i, num in enumerate(images)))

        page_ids = []
        for page in self.pages:
            content = zlib.compress(b'\n'.join(page))
            stream = add('<< /Length {} /Filter /FlateDecode >>\nstream\n'.format(len(content)).encode() + content + b'\nendstream')
            page_ids.append(add('<< /Type /Page /Parent {} 0 R /MediaBox [0 0 {:.2f} {:.2f}] /Resources {} /Contents {} 0 R >>'.format(
                pages, self.width, self.height, resources, stream).encode()))

        objects[catalog - 1] = '<< /Type /Catalog /Pages {} 0 R >>'.format(pages).encode()
        objects[pages - 1] = '<< /Type /Pages /Kids [{}] /Count {} >>'.format(
            ' '.join('{} 0 R'.format(p) for p in page_ids), len(page_ids)).encode()

        out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = []
        for number, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += '{} 0 obj\n'.format(number).encode() + obj + b'\nendobj\n'

        xref = len(out)
        out += 'xref\n0 {}\n0000000000 65535 f \n'.format(len(objects) + 1).encode()
        for offset in offsets:
            out += '{:010d} 00000 n \n'.format(offset).encode()
        out += 'trailer\n<< /Size {} /Root {} 0 R >>\nstartxref\n{}\n%%EOF\n'.format(len(objects) + 1, catalog, xref).encode()

        with open(path, 'wb') as f:
            f.write(out)
