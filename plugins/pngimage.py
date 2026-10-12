'''
Tiny PNG reader (standard library only, KiCad's Python has no imaging library).
Supports the 8 bit RGB / RGBA non-interlaced PNGs written by kicad-cli pcb render.
'''
import struct
import zlib


def _unfilter(data, width, height, bpp):
    stride = width * bpp
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = data[pos]
        row = bytearray(data[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:      # Sub
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif ftype == 2:    # Up
            row = bytearray((a + b) & 0xFF for a, b in zip(row, prev))
        elif ftype == 3:    # Average
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif ftype == 4:    # Paeth
            for x in range(stride):
                a = row[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return out


def read_png(path):
    '''Returns (width, height, rgb bytes, alpha bytes or None).'''
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Not a PNG file: {}'.format(path))

    pos, idat = 8, []
    while pos < len(data):
        length, ctype = struct.unpack('>I4s', data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b'IHDR':
            width, height, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', chunk)
        elif ctype == b'IDAT':
            idat.append(chunk)
        elif ctype == b'IEND':
            break
        pos += 12 + length

    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError('Unsupported PNG format (depth {}, color type {}, interlace {})'.format(depth, color, interlace))

    bpp = 4 if color == 6 else 3
    pixels = _unfilter(zlib.decompress(b''.join(idat)), width, height, bpp)
    if bpp == 3:
        return width, height, bytes(pixels), None

    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = pixels[0::4], pixels[1::4], pixels[2::4]
    return width, height, bytes(rgb), bytes(pixels[3::4])


def crop_transparent(width, height, rgb, alpha, margin=4):
    '''Crops the fully transparent border around the board.'''
    if alpha is None:
        return width, height, rgb, alpha
    rows = [y for y in range(height) if alpha[y * width:(y + 1) * width].strip(b'\x00')]
    if not rows:
        return width, height, rgb, alpha
    left, right = width, 0
    for y in rows:
        line = alpha[y * width:(y + 1) * width]
        left = min(left, len(line) - len(line.lstrip(b'\x00')))
        right = max(right, len(line.rstrip(b'\x00')))
    top, bottom = max(rows[0] - margin, 0), min(rows[-1] + 1 + margin, height)
    left, right = max(left - margin, 0), min(right + margin, width)

    w, h = right - left, bottom - top
    new_rgb = b''.join(rgb[(y * width + left) * 3:(y * width + right) * 3] for y in range(top, bottom))
    new_alpha = b''.join(alpha[y * width + left:y * width + right] for y in range(top, bottom))
    return w, h, new_rgb, new_alpha
