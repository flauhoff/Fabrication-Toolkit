'''
Three-view drawing of the board in first angle projection (ISO 128, "Projektionsmethode 1"),
arranged vertically:

    Oberseite                 view onto the top side
    Seitenansicht             view onto the long edge, seen from above the Oberseite
    Unterseite                view onto the bottom side, seen from above the Seitenansicht

All views have the same scale and are aligned on the board center. In first angle projection
the view drawn below another one is the view from ABOVE it, so in the Seitenansicht the
components of the top side point down (towards the Unterseite) and the Unterseite shows the
board with the upper board edge at the bottom.

The kicad-cli renders are rotated / mirrored in the PDF (no pixel processing). Camera axes of
`kicad-cli pcb render --side ...` as (image right, image up) in board coordinates
(X right, Y up = towards the top of the PCB editor, Z = out of the top side):
'''

CAMERA_AXES = {
    'top':    ('+X', '+Y'),
    'bottom': ('-X', '+Y'),
    'front':  ('+X', '+Z'),   # camera at the lower board edge
    'back':   ('-X', '+Z'),   # camera at the upper board edge
    'left':   ('-Y', '+Z'),
    'right':  ('+Y', '+Z'),
}

SIDE_OF = {'+Y': 'back', '-Y': 'front', '+X': 'right', '-X': 'left'}


def _neg(axis):
    return ('-' if axis[0] == '+' else '+') + axis[1]


def _dot(a, b):
    if a[1] != b[1]:
        return 0
    return 1 if a[0] == b[0] else -1


def plan(board_width, board_height):
    '''
    Returns [(caption, render side, (image right, image up) wanted on the page), ...].
    The long board side is drawn horizontally.
    '''
    if board_width >= board_height:
        right, up = '+X', '+Y'
    else:
        right, up = '-Y', '+X'   # top view turned by 90°, long side horizontal
    return [
        ('OBERSEITE', 'top', (right, up)),
        ('SEITENANSICHT', SIDE_OF[up], (right, '-Z')),     # seen from +up
        ('UNTERSEITE', 'bottom', (right, _neg(up))),       # seen from -Z
    ]


def page_matrix(side, wanted):
    '''
    2x2 matrix (as ((a, b), (c, d))) mapping image directions of the render to page directions:
    image right -> (a, b), image up -> (c, d), page coordinates with y up.
    '''
    source_right, source_up = CAMERA_AXES[side]
    page_right, page_up = wanted
    return ((_dot(source_right, page_right), _dot(source_right, page_up)),
            (_dot(source_up, page_right), _dot(source_up, page_up)))
