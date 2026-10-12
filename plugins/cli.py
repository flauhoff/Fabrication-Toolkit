import argparse as ap

from .thread import ProcessThread
from .options import *


if __name__ == '__main__':
    parser = ap.ArgumentParser(prog="Schienle_PCB_Freigabe",
                            description="Generates production files and an indexed project archive from a KiCAD board file")

    parser.add_argument("--path",               "-p",  type=str, help="Path to KiCAD board file", required=True)
    parser.add_argument("--additionalLayers",   "-aL", type=str, help="Additional layers(comma-separated)", metavar="LAYERS")
    parser.add_argument("--user1VCut",          "-u1", action="store_true", help="Set User.1 as V-Cut layer")
    parser.add_argument("--user2AltVCut",       "-u2", action="store_true", help="Set User.2 as alternative Edge-Cut layer")
    parser.add_argument("--autoTranslate",      "-t",  action="store_true", help="Apply automatic position/rotation translations")
    parser.add_argument("--autoFill",           "-f",  action="store_true", help="Apply automatic fill for all zones")
    parser.add_argument("--excludeDNP",         "-e",  action="store_true", help="Exclude DNP components from BOM")
    parser.add_argument("--allActiveLayers",    "-aaL",action="store_true", help="Export all active layers instead of only commonly used ones")
    parser.add_argument("--archiveName",        "-aN", type=str, help="Name of the generated archives", metavar="NAME")
    parser.add_argument("--openBrowser",        "-b",  action="store_true", help="Open webbrowser with directory file overview after generation")
    parser.add_argument("--nonInteractive",     "-nI" ,action="store_true", help="Run in non-Interactive mode. Useful in CI/CD environment.")
    parser.add_argument("--noBackup",           "-nB", action="store_true", help="Do not create backup files")
    parser.add_argument("--drawingNumber",      "-dn", type=str, help="Drawing number (Zeichnungsnummer) of this release", metavar="NUMBER")
    parser.add_argument("--index",              "-i",  type=str, help="Index of this release (e.g. A, B, 01)", metavar="INDEX")
    parser.add_argument("--setRevision",        "-sR", action="store_true", help="Write the index into the title block revision and save the board")
    parser.add_argument("--stepExport",         "-st", action="store_true", help="Export the 3D model as STEP (requires KiCad 7+)")
    parser.add_argument("--schematicPdf",       "-sp", action="store_true", help="Export the schematic as PDF (release only, requires KiCad 7+)")
    parser.add_argument("--projectBackup",      "-pB", action="store_true", help="Add a zipped project backup to the release")
    parser.add_argument("--overwrite",          "-o",  action="store_true", help="Overwrite an existing release with the same drawing number and index")
    args = parser.parse_args()

    if bool(args.drawingNumber) != bool(args.index):
        parser.error("a release requires both --drawingNumber and --index")
    if args.setRevision and not args.index:
        parser.error("--setRevision requires --index")

    options = dict()
    options[AUTO_TRANSLATE_OPT] = args.autoTranslate
    options[AUTO_FILL_OPT] = args.autoFill
    options[EXCLUDE_DNP_OPT] = args.excludeDNP
    options[EXTEND_EDGE_CUT_OPT] = args.user1VCut
    options[ALTERNATIVE_EDGE_CUT_OPT] = args.user2AltVCut
    options[ALL_ACTIVE_LAYERS_OPT] = args.allActiveLayers
    options[ARCHIVE_NAME] = args.archiveName
    options[EXTRA_LAYERS] = args.additionalLayers
    options[BACKUP_OPT] = not args.noBackup
    options[INDEX_OPT] = args.index
    options[SET_REVISION_OPT] = args.setRevision
    options[DRAWING_NO_OPT] = args.drawingNumber
    options[SCHEMATIC_PDF_OPT] = args.schematicPdf
    options[PROJECT_BACKUP_OPT] = args.projectBackup
    options[OVERWRITE_RELEASE_OPT] = args.overwrite
    options[STEP_EXPORT_OPT] = args.stepExport
    
    openBrowser = args.openBrowser
    nonInteractive = args.nonInteractive


    path = args.path

    ProcessThread(wx=None, cli=path, options=options, openBrowser=openBrowser, nonInteractive=nonInteractive)
