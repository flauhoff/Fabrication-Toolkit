import argparse as ap

from .thread import ProcessThread
from .options import *


if __name__ == '__main__':
    parser = ap.ArgumentParser(prog="Schienle_PCB_Freigabe",
                               description="Erstellt eine PCB-Freigabe (DRC, Fertigungsdaten, STEP, Schaltplan-PDF, "
                                           "Projekt-Backup) in Freigaben/<Zeichnungsnummer>_<Index>/")

    parser.add_argument("--path",               "-p",  type=str, help="Pfad zur KiCad-Platine (.kicad_pcb)", required=True)
    parser.add_argument("--drawingNumber",      "-dn", type=str, help="Zeichnungsnummer der Freigabe", metavar="NUMMER", required=True)
    parser.add_argument("--index",              "-i",  type=str, help="Index der Freigabe (z. B. A, B, 01)", metavar="INDEX", required=True)
    parser.add_argument("--setRevision",        "-sR", action="store_true", help="Index in die Revision des Platinen-Schriftfelds schreiben")
    parser.add_argument("--autoFill",           "-f",  action="store_true", help="Alle Zonen vor der Freigabe füllen")
    parser.add_argument("--stepExport",         "-st", action="store_true", help="3D-Modell als STEP exportieren")
    parser.add_argument("--schematicPdf",       "-sp", action="store_true", help="Schaltplan als PDF exportieren")
    parser.add_argument("--projectBackup",      "-pB", action="store_true", help="Projekt-Backup erstellen")
    parser.add_argument("--overwrite",          "-o",  action="store_true", help="Bestehende Freigabe mit gleicher Zeichnungsnummer und gleichem Index überschreiben")
    parser.add_argument("--openBrowser",        "-b",  action="store_true", help="Freigabeordner danach öffnen")
    parser.add_argument("--nonInteractive",     "-nI", action="store_true", help="Ohne Fortschrittsanzeige (z. B. für CI)")
    # fabrication data (advanced, from the original Fabrication Toolkit)
    parser.add_argument("--additionalLayers",   "-aL", type=str, help="Zusätzliche Lagen für die Gerberdaten (kommagetrennt)", metavar="LAGEN")
    parser.add_argument("--allActiveLayers",    "-aaL", action="store_true", help="Alle aktiven Lagen plotten")
    parser.add_argument("--user1VCut",          "-u1", action="store_true", help="User.1 als V-Cut-Lage verwenden")
    parser.add_argument("--user2AltVCut",       "-u2", action="store_true", help="User.2 als alternative Kontur verwenden")
    parser.add_argument("--autoTranslate",      "-t",  action="store_true", help="JLC-Bestückungskorrekturen (Rotation/Position) anwenden")
    parser.add_argument("--excludeDNP",         "-e",  action="store_true", help="DNP-Bauteile aus der Stückliste ausschließen")
    args = parser.parse_args()

    options = dict()
    options[DRAWING_NO_OPT] = args.drawingNumber
    options[INDEX_OPT] = args.index
    options[SET_REVISION_OPT] = args.setRevision
    options[AUTO_FILL_OPT] = args.autoFill
    options[STEP_EXPORT_OPT] = args.stepExport
    options[SCHEMATIC_PDF_OPT] = args.schematicPdf
    options[PROJECT_BACKUP_OPT] = args.projectBackup
    options[OVERWRITE_RELEASE_OPT] = args.overwrite
    options[EXTRA_LAYERS] = args.additionalLayers
    options[ALL_ACTIVE_LAYERS_OPT] = args.allActiveLayers
    options[EXTEND_EDGE_CUT_OPT] = args.user1VCut
    options[ALTERNATIVE_EDGE_CUT_OPT] = args.user2AltVCut
    options[AUTO_TRANSLATE_OPT] = args.autoTranslate
    options[EXCLUDE_DNP_OPT] = args.excludeDNP

    ProcessThread(wx=None, cli=args.path, options=options, openBrowser=args.openBrowser, nonInteractive=args.nonInteractive)
