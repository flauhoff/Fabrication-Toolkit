import argparse as ap

from .thread import ProcessThread
from .options import *


if __name__ == '__main__':
    parser = ap.ArgumentParser(prog="Fabrication Toolkit",
                            description="Generates JLCPCB production files from a KiCAD board file")

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
    parser.add_argument("--index",              "-i",  type=str, help="Index of this release (e.g. A, B, 01)", metavar="INDEX")
    parser.add_argument("--setRevision",        "-sR", action="store_true", help="Write the index into the title block revision and save the board")
    parser.add_argument("--archiveProject",     "-aP", action="store_true", help="Archive the complete project as archive/<project>_Index_<INDEX>.zip")
    parser.add_argument("--overwriteArchive",   "-oA", action="store_true", help="Overwrite an existing project archive of the same index")
    args = parser.parse_args()

    if (args.setRevision or args.archiveProject) and not args.index:
        parser.error("--setRevision and --archiveProject require --index")

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
    options[ARCHIVE_PROJECT_OPT] = args.archiveProject
    options[OVERWRITE_ARCHIVE_OPT] = args.overwriteArchive
    
    openBrowser = args.openBrowser
    nonInteractive = args.nonInteractive


    path = args.path

    ProcessThread(wx=None, cli=path, options=options, openBrowser=openBrowser, nonInteractive=nonInteractive)
