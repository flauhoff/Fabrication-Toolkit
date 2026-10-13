# For better annotation.
from __future__ import annotations

# System base libraries
import os
import re
import csv
import math
import shutil
from collections import defaultdict
from typing import Tuple

# Interaction with KiCad: board data via the IPC API, plots via kicad-cli (on the saved board file).
from kipy.proto.board.board_types_pb2 import BoardLayer
from .kicad_board import layer_canonical_name
from .kicad_cli import export_gerbers, export_gerber, export_drill, export_ipcd356

# Application definitions.
from .config import *

class ProcessManager:
    def __init__(self, board, logger = None):
        # board: kicad_board.BoardAccess of the board opened in KiCad
        self.board = board
        self.logger = logger
        self.bom = []
        self.components = []
        self.__rotation_db = self.__read_rotation_db()

    @staticmethod
    def normalize_filename(filename):
        return re.sub(r'[^\w\s\.\-]', '', filename)

    @staticmethod
    def _format_coordinate(value, precision=6):
        '''Round off floating-point residue and render as fixed-point (never scientific) notation.'''
        value = round(value, precision)
        if value == 0:
            value = 0.0  # avoid "-0"
        return f'{value:.{precision}f}'.rstrip('0').rstrip('.') or '0'

    def update_zone_fills(self):
        '''Refills all zones in KiCad.'''
        self.board.refill_zones()

    def generate_gerber(self, temp_dir, extra_layers, extend_edge_cuts, alternative_edge_cuts, all_active_layers):
        '''Generate the Gerber files (kicad-cli, from the saved board file).'''
        if extra_layers is not None:
            extra_layers = [element.strip() for element in extra_layers.strip().split(',') if element.strip()]
        else:
            extra_layers = []
        extra_layer_ids = [layer for layer in (self.board.layer_by_name(name) for name in extra_layers) if layer is not None]

        layers = [layer for layer in self.board.enabled_layers() if all_active_layers or layer in standardLayers]
        layers += [layer for layer in extra_layer_ids if layer not in layers]
        merge_edge_cuts = BoardLayer.BL_Edge_Cuts in layers and (extend_edge_cuts or alternative_edge_cuts)
        if merge_edge_cuts:
            layers.remove(BoardLayer.BL_Edge_Cuts)

        board_file = self.board.file_path
        if layers:
            export_gerbers(board_file, temp_dir, [layer_canonical_name(layer) for layer in layers], logger=self.logger)

        if merge_edge_cuts:
            # uses User.2 as alternative Edge.Cuts layer, includes User.1 with Edge.Cuts to allow V-cuts on User.1
            edge_layers = [BoardLayer.BL_User_2] if alternative_edge_cuts else [BoardLayer.BL_Edge_Cuts]
            if extend_edge_cuts:
                edge_layers += [BoardLayer.BL_Edge_Cuts, BoardLayer.BL_User_1]
            edge_layers = list(dict.fromkeys(edge_layers))

            board_name = os.path.splitext(os.path.basename(board_file))[0]
            output_file = os.path.join(temp_dir, '{}-{}.gm1'.format(board_name, self.board.layer_name(BoardLayer.BL_Edge_Cuts).replace('.', '_')))
            export_gerber(board_file, output_file, [layer_canonical_name(layer) for layer in edge_layers], logger=self.logger)

    def generate_drills(self, temp_dir):
        '''Generate the drill files (kicad-cli).'''
        export_drill(self.board.file_path, temp_dir, logger=self.logger)

    def generate_netlist(self, temp_dir):
        '''Generate the connection netlist (kicad-cli).'''
        export_ipcd356(self.board.file_path, os.path.join(temp_dir, netlistFileName), logger=self.logger)

    def _get_footprint_position(self, footprint):
        """Position based on the anchor (SMD) or the center of the pads (THT), see _get_origin_from_footprint."""
        if self._get_origin_from_footprint(footprint) == 'Anchor':
            return footprint.position
        return self.board.pads_center(footprint)

    def generate_tables(self, temp_dir, auto_translate, exclude_dnp):
        '''Generate the data tables.'''
        footprints = self.board.footprints()
        aux_origin = self.board.drill_origin()

        # sort footprint after designator
        footprints.sort(key=lambda x: x.reference.upper())

        # unique designator dictionary
        footprint_designators = defaultdict(int)
        for i, footprint in enumerate(footprints):
            # count unique designators
            footprint_designators[footprint.reference.upper()] += 1
        bom_designators = footprint_designators.copy()

        if len(footprint_designators.items()) > 0:
            with open((os.path.join(temp_dir, designatorsFileName)), 'w', encoding='utf-8-sig') as f:
                for key, value in footprint_designators.items():
                    f.write('%s:%s\n' % (key, value))

        for i, footprint in enumerate(footprints):
            footprint_name = footprint.footprint_name

            # Get the library nickname when available
            lib_nickname = footprint.library_nickname

            layer = self._get_layer_override_from_footprint(footprint)

            # mount_type = {
            #     0: 'smt',
            #     1: 'tht',
            #     2: 'unspecified'
            # }.get(footprint.GetAttributes())

            is_dnp = (footprint.has_field('dnp')
                      or (footprint.value.upper() == 'DNP')
                      or footprint.is_dnp)
            skip_dnp = exclude_dnp and is_dnp

            if not footprint.exclude_from_pos_files and not is_dnp:
                # append unique ID if duplicate footprint designator
                unique_id = ""
                if footprint_designators[footprint.reference.upper()] > 1:
                    unique_id = str(footprint_designators[footprint.reference.upper()])
                    footprint_designators[footprint.reference.upper()] -= 1

                designator = "{}{}{}".format(footprint.reference.upper(), "" if unique_id == "" else "_", unique_id)
                position = self._get_footprint_position(footprint)
                mid_x = (position[0] - aux_origin.x) / 1000000.0
                mid_y = (position[1] - aux_origin.y) * -1.0 / 1000000.0
                rotation = footprint.rotation
                rotation_offset_db = self._get_rotation_from_db(footprint_name, lib_nickname) # Try with lib_nickname if available
                rotation_offset_manual = self._get_rotation_offset_from_footprint(footprint)

                # position offset needs to take rotation into account
                pos_offset = self._get_position_offset_from_footprint(footprint)
                if auto_translate:
                    pos_offset_db = self._get_position_offset_from_db(footprint_name, lib_nickname) # Try with lib_nickname if available
                    pos_offset = (pos_offset[0] + pos_offset_db[0], pos_offset[1] + pos_offset_db[1])

                rsin = math.sin(rotation / 180 * math.pi)
                rcos = math.cos(rotation / 180 * math.pi)

                if layer == 'bottom':
                    pos_offset = ( pos_offset[0] * rcos + pos_offset[1] * rsin, pos_offset[0] * rsin - pos_offset[1] * rcos )
                else:
                    pos_offset = ( pos_offset[0] * rcos - pos_offset[1] * rsin, pos_offset[0] * rsin + pos_offset[1] * rcos )
                mid_x, mid_y = tuple(map(sum,zip((mid_x, mid_y), pos_offset)))

                # JLC expect 'Rotation' to be 'as viewed from above component', so bottom needs inverting, and ends up 180 degrees out as well
                if layer == 'bottom':
                    rotation = (180.0 - rotation)

                if auto_translate:
                    rotation += rotation_offset_db

                rotation = (rotation + rotation_offset_manual) % 360.0

                self.components.append({
                    'Designator': designator,
                    'Mid X': self._format_coordinate(mid_x),
                    'Mid Y': self._format_coordinate(mid_y),
                    'Rotation': self._format_coordinate(rotation),
                    'Layer': layer,
                })

            if not footprint.exclude_from_bom and not skip_dnp:
                # append unique ID if we are dealing with duplicate bom designator
                unique_id = ""
                if bom_designators[footprint.reference.upper()] > 1:
                    unique_id = str(bom_designators[footprint.reference.upper()])
                    bom_designators[footprint.reference.upper()] -= 1

                # merge similar parts into single entry
                insert = True
                for component in self.bom:
                    same_footprint = component['Footprint'] == self._normalize_footprint_name(footprint_name)
                    same_value = component['Value'].upper() == footprint.value.upper()
                    same_lcsc = component['LCSC Part #'] == self._get_mpn_from_footprint(footprint)
                    under_limit = component['Quantity'] < bomRowLimit

                    if same_footprint and same_value and same_lcsc and under_limit:
                        component['Designator'] += ", " + "{}{}{}".format(footprint.reference.upper(), "" if unique_id == "" else "_", unique_id)
                        component['Quantity'] += 1
                        insert = False
                        break

                # add component to BOM
                if insert:
                    self.bom.append({
                        'Designator': "{}{}{}".format(footprint.reference.upper(), "" if unique_id == "" else "_", unique_id),
                        'Footprint': self._normalize_footprint_name(footprint_name),
                        'Quantity': 1,
                        'Value': footprint.value,
                        # 'Mount': mount_type,
                        'LCSC Part #': self._get_mpn_from_footprint(footprint),
                    })

    def generate_positions(self, temp_dir):
        '''Generate the position file.'''
        if len(self.components) > 0:
            with open((os.path.join(temp_dir, placementFileName)), 'w', newline='', encoding='utf-8-sig') as outfile:
                csv_writer = csv.writer(outfile)
                # writing headers of CSV file
                csv_writer.writerow(self.components[0].keys())

                for component in self.components:
                    # writing data of CSV file
                    if ('**' not in component['Designator']):
                        csv_writer.writerow(component.values())

    def generate_bom(self, temp_dir):
        '''Generate the bom file.'''
        if len(self.bom) > 0:
            with open((os.path.join(temp_dir, bomFileName)), 'w', newline='', encoding='utf-8-sig') as outfile:
                csv_writer = csv.writer(outfile)
                # writing headers of CSV file
                csv_writer.writerow(self.bom[0].keys())

                # Output all of the component information
                for component in self.bom:
                    # writing data of CSV file
                    if ('**' not in component['Designator']):
                        csv_writer.writerow(component.values())

    def generate_archive(self, temp_dir, temp_file):
        '''Generate the archive file.'''
        temp_file = shutil.make_archive(temp_file, 'zip', temp_dir)
        temp_file = shutil.move(temp_file, temp_dir)

        # remove non essential files
        for item in os.listdir(temp_dir):
            if not item.endswith(".zip") and not item.endswith(".csv") and not item.endswith(".ipc"):
                os.remove(os.path.join(temp_dir, item))

        return temp_file

    """ Private """

    def __read_rotation_db(self, filename: str = os.path.join(os.path.dirname(__file__), 'transformations.csv')) -> dict[str, float]:
        '''Read the rotations.cf config file so we know what rotations
        to apply later.
        '''
        db = {}

        with open(filename, newline='') as csvfile:
            csvDialect = csv.Sniffer().sniff(csvfile.read(1024))
            csvfile.seek(0)
            csvData = csv.DictReader(csvfile, fieldnames=["footprint", "rotation", "x", "y"],
                                     restkey="extra", restval="0", dialect=csvDialect)

            rowNum = 0
            for row in csvData:
                    rowNum = rowNum + 1
                    # First row is header row, skip.
                    if rowNum == 1:
                        skipFirst = False
                        continue

                    # If there was too many fields, throw an exception.
                    if len(row) > 4:
                        raise RuntimeError("{}: Too many fields found in row {}: {}".format(filename, rowNum, row))

                    # See if the values we expect to be floating point numbers
                    # can be converted to floating point, if not throw an exception.
                    if row['rotation'] == "":
                        rotation = 0.0
                    else:
                        try:
                            rotation = float(row['rotation'])
                        except ValueError:
                            raise RuntimeError("{}: Non-numeric rotation value found in row {}".format(filename, rowNum))

                    if row['x'] == "":
                        delta_x = 0.0
                    else:
                        try:
                            delta_x  = float(row['x'])
                        except ValueError:
                            raise RuntimeError("{}: Non-numeric translation value found in row {}".format(filename, rowNum))

                    if row['y'] == "":
                        delta_y = 0.0
                    else:
                        try:
                            delta_y  = float(row['y'])
                        except ValueError:
                            raise RuntimeError("{}: Non-numeric translation value found in row {}".format(filename, rowNum))

                    # Add the entry to the database in the format we expect.
                    db[rowNum] = {}
                    db[rowNum]['name'] = row['footprint']
                    db[rowNum]['rotation'] = rotation
                    db[rowNum]['x'] = delta_x
                    db[rowNum]['y'] = delta_y

        return db

    def _get_rotation_from_db(self, footprint: str, lib_nickname: str = None) -> float:
        '''Get the rotation to be added from the database file.

        Args:
            footprint: The footprint name
            lib_nickname: The library nickname, if available
        '''
        # First try with the standard approach for backward compatibility
        for entry in self.__rotation_db.items():
            # If the expression in the DB contains a :, search for it literally.
            if (re.search(':', entry[1]['name'])):
                if (re.search(entry[1]['name'], footprint)):
                    return float(entry[1]['rotation'])
            # There is no : in the expression, so only search the right side of the :
            else:
                footprint_segments = footprint.split(':')
                # Only one means there was no :, just check the short.
                if (len(footprint_segments) == 1):
                    check = footprint_segments[0]
                # More means there was a :, check the right side.
                else:
                    check = footprint_segments[1]
                if (re.search(entry[1]['name'], check)):
                    return float(entry[1]['rotation'])

        # If no match found and we have a library nickname, try matching against that
        if lib_nickname:
            for entry in self.__rotation_db.items():
                if (re.search(entry[1]['name'], lib_nickname)):
                    return float(entry[1]['rotation'])

        # Not found, no rotation.
        return 0.0

    def _get_position_offset_from_db(self, footprint: str, lib_nickname: str = None) -> Tuple[float, float]:
        '''Get the position offset to be added from the database file.

        Args:
            footprint: The footprint name
            lib_nickname: The library nickname, if available
        '''
        # First try with the standard approach for backward compatibility
        for entry in self.__rotation_db.items():
            # If the expression in the DB contains a :, search for it literally.
            if (re.search(':', entry[1]['name'])):
                if (re.search(entry[1]['name'], footprint)):
                    return ( float(entry[1]['x']), float(entry[1]['y']) )
            # There is no : in the expression, so only search the right side of the :
            else:
                footprint_segments = footprint.split(':')
                # Only one means there was no :, just check the short.
                if (len(footprint_segments) == 1):
                    check = footprint_segments[0]
                # More means there was a :, check the right side.
                else:
                    check = footprint_segments[1]
                if (re.search(entry[1]['name'], check)):
                    return (float(entry[1]['x']), float(entry[1]['y']))

        # If no match found and we have a library nickname, try matching against that
        if lib_nickname:
            for entry in self.__rotation_db.items():
                if (re.search(entry[1]['name'], lib_nickname)):
                    return (float(entry[1]['x']), float(entry[1]['y']))

        # Not found, no delta.
        return (0.0, 0.0)

    def _get_mpn_from_footprint(self, footprint) -> str:
        ''''Get the MPN/LCSC stock code from standard symbol fields.'''
        supplier_names = ['LCSC', 'JLCPCB']
        pn_abbrevs = ['Part #', 'Part', 'PN', 'P/N', 'Part No.', 'Part Number']
        keys = [(sn + " " + abr) for sn in supplier_names for abr in pn_abbrevs]
        fallback_keys = ['LCSC', 'JLC', 'MPN', 'Mpn', 'mpn']

        if footprint.has_field('dnp'):
            return 'DNP'

        for key in keys + fallback_keys:
            if footprint.has_field(key) and '' != footprint.get_field(key):
                return footprint.get_field(key)

    def _get_layer_override_from_footprint(self, footprint) -> str:
        '''Get the layer override from standard symbol fields.'''
        keys = ['FT Layer Override']
        fallback_keys = ['Layer Override', 'LayerOverride']

        layer = 'bottom' if footprint.is_bottom else ('top' if footprint.is_top else None)

        for key in keys + fallback_keys:
            if footprint.has_field(key):
                temp_layer = footprint.get_field(key)
                if len(temp_layer) > 0:
                    if (temp_layer[0] == 'b' or temp_layer[0] == 'B'):
                        layer = "bottom"
                        break
                    elif (temp_layer[0] == 't' or temp_layer[0] == 'T'):
                        layer = "top"
                        break

        return layer

    def _get_rotation_offset_from_footprint(self, footprint) -> float:
        '''Get the rotation offset from standard symbol fields.'''
        keys = ['FT Rotation Offset']
        fallback_keys = ['Rotation Offset', 'RotOffset']

        offset = ""

        for key in keys + fallback_keys:
            if footprint.has_field(key):
                offset = footprint.get_field(key)
                break

        if offset is None or offset == "":
            return 0.0
        else:
            try:
                return float(offset)
            except ValueError:
                raise RuntimeError("Rotation offset of {} is not a valid number".format(footprint.reference))

    def _get_position_offset_from_footprint(self, footprint) -> Tuple[float, float]:
        '''Get the position offset from standard symbol fields.'''
        keys = ['FT Position Offset']
        fallback_keys = ['Position Offset', 'PosOffset']

        offset = ""

        for key in keys + fallback_keys:
            if footprint.has_field(key):
                offset = footprint.get_field(key)
                break

        if offset == "":
            return (0.0, 0.0)
        else:
            try:
                offset = offset.split(",")
                return (float(offset[0]), float(offset[1]))
            except Exception as e:
                raise RuntimeError("Position offset of {} is not a valid pair of numbers".format(footprint.reference))

    def _get_origin_from_footprint(self, footprint) -> float:
        '''Get the origin from standard symbol fields.'''
        keys = ['FT Origin']
        fallback_keys = ['Origin']

        # determine origin type by package type
        if footprint.is_smd:
            origin_type = 'Anchor'
        else:
            origin_type = 'Center'

        for key in keys + fallback_keys:
            if footprint.has_field(key):
                origin_type_override = str(footprint.get_field(key)).strip().capitalize()

                if origin_type_override in ['Anchor', 'Center']:
                    origin_type = origin_type_override
                break

        return origin_type

    def _normalize_footprint_name(self, footprint) -> str:
        # replace footprint names of resistors, capacitors, inductors, diodes, LEDs, fuses etc, with the footprint size only
        pattern = re.compile(r'^(\w*_SMD:)?\w{1,4}_(\d+)_\d+Metric.*$')

        return pattern.sub(r'\2', footprint)
