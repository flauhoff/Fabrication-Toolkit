'''Access to the board opened in KiCad via the IPC API (kicad-python), replacing the SWIG `pcbnew` module.'''
import os
import math
import time

from kipy import KiCad
from kipy.board_types import Field
from kipy.proto.board.board_types_pb2 import BoardLayer, FootprintMountingStyle
from kipy.proto.board.board_commands_pb2 import BoardOriginType


def layer_canonical_name(layer):
    '''KiCad standard name of a layer, e.g. BL_F_Cu -> F.Cu, BL_Edge_Cuts -> Edge.Cuts, BL_User_1 -> User.1'''
    name = BoardLayer.Name(layer)[3:]
    return name.replace('_', '.', 1)


def layer_from_canonical_name(name):
    return BoardLayer.Value('BL_' + name.replace('.', '_', 1))


def connect():
    '''Connects to the running KiCad instance (socket and token are passed by KiCad in the environment).'''
    return KiCad()


class BoardAccess:
    '''Thin wrapper around the kipy board, offering what the release workflow needs.'''

    def __init__(self, kicad, board):
        self.kicad = kicad
        self.board = board

    @classmethod
    def open(cls, kicad=None):
        kicad = kicad or connect()
        return cls(kicad, kicad.get_board())

    # --- files -----------------------------------------------------------------

    @property
    def file_path(self):
        project_dir = self.board.get_project().path
        return os.path.join(project_dir, self.board.name)

    @property
    def project_directory(self):
        return os.path.dirname(self.file_path)

    def save(self):
        self.board.save()

    def kicad_cli_path(self):
        try:
            return self.kicad.get_kicad_binary_path('kicad-cli')
        except Exception:
            return None

    # --- title block / text variables -----------------------------------------

    def title_block(self):
        return self.board.get_title_block_info()

    def set_revision(self, revision):
        title_block = self.board.get_title_block_info()
        title_block.revision = revision
        self.board.set_title_block_info(title_block)

    def expand_text_variables(self, text):
        if not text or '${' not in text:
            return text
        try:
            return self.board.expand_text_variables(text)
        except Exception:
            return text

    # --- layers ----------------------------------------------------------------

    def enabled_layers(self):
        return list(self.board.get_enabled_layers())

    def layer_name(self, layer):
        '''User visible (possibly customized) name of a layer.'''
        try:
            return self.board.get_layer_name(layer)
        except Exception:
            return layer_canonical_name(layer)

    def layer_by_name(self, name):
        '''Layer id of a user visible or standard layer name, None if unknown.'''
        try:
            return self.board.get_layer_by_name(name)
        except Exception:
            pass
        try:
            return layer_from_canonical_name(name)
        except ValueError:
            return None

    def layer_names(self):
        return [self.layer_name(layer) for layer in self.enabled_layers()]

    def copper_layer_count(self):
        return self.board.get_copper_layer_count()

    # --- geometry --------------------------------------------------------------

    def drill_origin(self):
        return self.board.get_origin(BoardOriginType.BOT_DRILL)

    def board_thickness(self):
        '''Board thickness in nm as sum of the stackup layers.'''
        return sum(layer.thickness for layer in self.board.get_stackup().layers)

    def board_edges_size(self):
        '''(width, height) in nm of the bounding box of the board outline (Edge.Cuts), None without outline.'''
        shapes = [shape for shape in self.board.get_shapes() if shape.layer == BoardLayer.BL_Edge_Cuts]
        boxes = self.board.get_item_bounding_box(shapes) if shapes else []
        if not boxes:
            return None

        left = min(box.pos.x for box in boxes)
        top = min(box.pos.y for box in boxes)
        right = max(box.pos.x + box.size.x for box in boxes)
        bottom = max(box.pos.y + box.size.y for box in boxes)
        return (right - left, bottom - top)

    # --- zones -----------------------------------------------------------------

    def refill_zones(self, timeout=600):
        '''Refills all zones and waits until KiCad answers again (it is busy while filling).
        kipy's own blocking wait gives up on the first transport timeout, so it is done here.'''
        self.board.refill_zones(block=False)
        deadline = time.time() + timeout
        while True:
            time.sleep(0.5)
            try:
                self.kicad.ping()
                return
            except Exception:
                if time.time() > deadline:
                    raise TimeoutError('KiCad did not finish filling the zones within {} s.'.format(timeout))

    # --- footprints ------------------------------------------------------------

    def footprints(self):
        return [Footprint(fp) for fp in self.board.get_footprints()]

    def pads_center(self, footprint):
        '''Center of the pads bounding box in the unrotated footprint frame, transformed back to board coordinates.
        Returns the footprint anchor if the footprint has no pads.'''
        fp = footprint.fp
        origin = fp.position
        pads = list(fp.definition.pads)
        if not pads:
            return (origin.x, origin.y)

        points = [pad.position for pad in pads]
        try:
            for polygon in self.board.get_pad_shapes_as_polygons(pads, fp.layer):
                points.extend(node.point for node in polygon.outline if node.has_point)
        except Exception:
            pass

        # KiCad rotates with x' = x*cos + y*sin, y' = y*cos - x*sin (y axis pointing down)
        angle = math.radians(footprint.rotation)
        rcos, rsin = math.cos(angle), math.sin(angle)

        local = []
        for point in points:
            dx, dy = point.x - origin.x, point.y - origin.y
            local.append((dx * rcos - dy * rsin, dy * rcos + dx * rsin))

        cx = (min(p[0] for p in local) + max(p[0] for p in local)) / 2
        cy = (min(p[1] for p in local) + max(p[1] for p in local)) / 2

        return (origin.x + cx * rcos + cy * rsin, origin.y + cy * rcos - cx * rsin)


class Footprint:
    '''Read-only view of a footprint instance with the fields the BOM / position files need.'''

    def __init__(self, fp):
        self.fp = fp

    @property
    def reference(self):
        return self.fp.reference_field.text.value

    @property
    def value(self):
        return self.fp.value_field.text.value

    @property
    def footprint_name(self):
        return self.fp.definition.id.name

    @property
    def library_nickname(self):
        return self.fp.definition.id.library or None

    @property
    def rotation(self):
        return self.fp.orientation.degrees

    @property
    def position(self):
        return (self.fp.position.x, self.fp.position.y)

    @property
    def is_bottom(self):
        return self.fp.layer == BoardLayer.BL_B_Cu

    @property
    def is_top(self):
        return self.fp.layer == BoardLayer.BL_F_Cu

    @property
    def is_smd(self):
        return self.fp.attributes.mounting_style == FootprintMountingStyle.FMS_SMD

    @property
    def is_dnp(self):
        return self.fp.attributes.do_not_populate

    @property
    def exclude_from_bom(self):
        return self.fp.attributes.exclude_from_bill_of_materials

    @property
    def exclude_from_pos_files(self):
        return self.fp.attributes.exclude_from_position_files

    def _field(self, name):
        for item in self.fp.texts_and_fields:
            if isinstance(item, Field) and item.name == name:
                return item
        return None

    def has_field(self, name):
        return self._field(name) is not None

    def get_field(self, name):
        field = self._field(name)
        return field.text.value if field is not None else None
