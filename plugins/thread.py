import os
import wx
import pcbnew  # type: ignore
import shutil
import tempfile
import webbrowser
import datetime
import time
import logging
import traceback
from threading import Thread
from .events import StatusEvent
from .process import ProcessManager
from .archive import backup_project, normalize_name, get_release_name, get_release_path, gerberFolder
from .archive import get_kicad_backups_path, get_kicad_backup_name
from .kicad_cli import export_step, export_schematic_pdf, run_drc, render_board, stepFileName
from .drc import load_drc_report, format_drc_summary
from .projectinfo import read_stackup
from .specpdf import write_spec_pdf
from . import spec
from .config import *
from .options import *
from .utils import print_cli_progress_bar, save_board, set_revision
from .debuglog import get_logger, log_environment

TITLE = 'Schienle_PCB_Freigabe'


class ProcessThread(Thread):
    def __init__(self, wx, options, cli = None, openBrowser = True, nonInteractive = False):
        Thread.__init__(self)

        # prevent use of cli and graphical mode at the same time
        if (wx is None and cli is None) or (wx is not None and cli is not None):
            logging.error("Specify either graphical or cli use!")
            return

        if cli is not None:
            try:
                self.board = pcbnew.LoadBoard(cli)
            except Exception as e:
                logging.error("%s - Fehler: %s", TITLE, e)
                return
        else:
            self.board = None

        self.process_manager = ProcessManager(self.board)
        self.wx = wx
        self.cli = cli
        self.options = options
        self.openBrowser = openBrowser
        self.nonInteractive = nonInteractive
        self.log = get_logger(os.path.dirname(self.process_manager.board.GetFileName()))
        self._step_started = None
        self.start()

    def step(self, percent, text):
        '''Reports progress, logs the step and its predecessor's duration and shows the step in the dialog.'''
        now = time.time()
        if self._step_started is not None:
            self.log.info('  ... fertig nach %.1f s', now - self._step_started[1])
        self._step_started = (text, now)
        self.log.info('[%3d%%] %s', percent, text)
        if self.wx is not None:
            wx.CallAfter(self._set_status_text, text)
        self.progress(percent)

    def _set_status_text(self, text):
        try:
            self.wx.setStatusText(text)
        except Exception:
            pass  # dialog already closed

    def error(self, title, message):
        '''Logs an error and shows it to the user (message boxes must be opened from the GUI thread).'''
        self.log.error('%s: %s', title, message)
        if self.wx is None:
            logging.error("%s - %s: %s", TITLE, title, message)
        else:
            wx.CallAfter(wx.MessageBox, message, "{} - {}".format(TITLE, title), wx.OK | wx.ICON_ERROR)

    def run(self):
        self.log.info('=' * 70)
        log_environment(self.log)
        self.log.info('Board: %s', self.process_manager.board.GetFileName())
        self.log.info('Optionen: %s', self.options)
        try:
            self._run()
        except Exception:
            # never die silently in the background thread
            self.log.error('Unerwarteter Fehler:\n%s', traceback.format_exc())
            self.error('Fehler', traceback.format_exc(limit=3))
            self.progress(100 if self.wx is None else -1)
        self.log.info('Beendet')

    def _run(self):
        self.step(0, 'Vorbereitung')

        temp_dir = tempfile.mkdtemp()
        temp_dir_gerber = temp_dir + "_g"
        os.makedirs(temp_dir_gerber)

        board_file = self.process_manager.board.GetFileName()
        project_directory = os.path.dirname(board_file)
        drawing_number = normalize_name(self.options.get(DRAWING_NO_OPT))
        index = normalize_name(self.options.get(INDEX_OPT))

        try:
            if not (drawing_number and index):
                raise ValueError('Für eine Freigabe werden Zeichnungsnummer und Index benötigt.')

            # kicad-cli (DRC, STEP, PDF, render) works on the saved files: fill zones, write the index into
            # the title block (so ${REVISION} on the board already shows it) and save the board.
            # In the GUI this is done by the dialog in the main thread (see plugin.py).
            if self.wx is None:
                if self.options[AUTO_FILL_OPT]:
                    self.step(3, 'Zonen füllen')
                    self.process_manager.update_zone_fills()
                self.step(6, 'Platine speichern')
                if self.options.get(SET_REVISION_OPT):
                    set_revision(self.process_manager.board, self.options[INDEX_OPT].strip())
                save_board(self.process_manager.board)

            # no release with DRC errors
            self.step(8, 'DRC läuft (kicad-cli)')
            report_file = os.path.join(temp_dir, 'drc.json')
            run_drc(board_file, report_file, logger=self.log)
            errors, warnings = load_drc_report(report_file)
            self.drc = (errors, warnings)
            self.log.info(format_drc_summary(errors, warnings))
            if errors:
                self.error('DRC fehlgeschlagen - keine Freigabe',
                           'Die Freigabe wurde NICHT erstellt, weil der DRC Fehler meldet.\n\n' + format_drc_summary(errors, warnings, limit=15))
                self.progress(100 if self.wx is None else -1)
                return
            os.remove(report_file)

            self.step(20, 'Gerberdaten erzeugen')
            self.process_manager.generate_gerber(temp_dir_gerber, self.options[EXTRA_LAYERS], self.options[EXTEND_EDGE_CUT_OPT],
                                                 self.options[ALTERNATIVE_EDGE_CUT_OPT], self.options[ALL_ACTIVE_LAYERS_OPT])

            self.step(30, 'Bohrdaten erzeugen')
            self.process_manager.generate_drills(temp_dir_gerber)

            self.step(40, 'Netzliste erzeugen')
            self.process_manager.generate_netlist(temp_dir)

            self.step(50, 'Bauteile sammeln')
            self.process_manager.generate_tables(temp_dir, self.options[AUTO_TRANSLATE_OPT], self.options[EXCLUDE_DNP_OPT])

            self.step(55, 'Bestückungsliste erzeugen')
            self.process_manager.generate_positions(temp_dir)

            self.step(60, 'Stückliste (BOM) erzeugen')
            self.process_manager.generate_bom(temp_dir)

            if self.options.get(STEP_EXPORT_OPT):
                self.step(65, 'STEP exportieren (kicad-cli, kann einige Minuten dauern)')
                try:
                    export_step(board_file, os.path.join(temp_dir, stepFileName), logger=self.log)
                except Exception as e:
                    self.error('Fehler beim STEP-Export', str(e))

            output_path = self._finish_release(temp_dir, temp_dir_gerber, board_file, project_directory, drawing_number, index)
        except Exception as e:
            self.log.error(traceback.format_exc())
            self.error('Fehler', str(e))
            self.progress(100 if self.wx is None else -1)
            return
        finally:
            for path in (temp_dir, temp_dir_gerber):
                shutil.rmtree(path, ignore_errors=True)

        self.step(99, 'Fertig: %s' % output_path)
        if self.openBrowser:
            webbrowser.open("file://%s" % (output_path))

        if self.wx is None:
            self.progress(100)
        else:
            self.progress(-1)

    def _finish_release(self, temp_dir, temp_dir_gerber, board_file, project_directory, drawing_number, index):
        '''
        Release structure:
            Freigaben/<drawing number>_<index>/
                Gerberdaten/                      gerber + drill files (not zipped)
                <name>_bom.csv, _positions.csv, _designators.csv, _netlist.ipc, .step
                <name>_Schaltplan.pdf, <name>_Leiterplattenspezifikation.pdf, <name>_DRC-Bericht.txt
                <name>_Projekt-Backup.zip
        '''
        name = get_release_name(drawing_number, index)
        release_path = get_release_path(board_file, drawing_number, index)
        self.log.info('Freigabe: %s', release_path)

        if os.path.exists(release_path):
            if not self.options.get(OVERWRITE_RELEASE_OPT):
                raise FileExistsError('Die Freigabe "{}" existiert bereits:\n{}'.format(name, release_path))
            self.log.info('Bestehende Freigabe wird überschrieben')
            shutil.rmtree(release_path)

        with open(os.path.join(temp_dir, name + '_DRC-Bericht.txt'), 'w', encoding='utf-8') as f:
            f.write(format_drc_summary(*self.drc) + '\n')

        # fabrication files with the release name
        renames = {
            netlistFileName: name + '_netlist.ipc',
            designatorsFileName: name + '_designators.csv',
            placementFileName: name + '_positions.csv',
            bomFileName: name + '_bom.csv',
            stepFileName: name + '.step',
        }
        for source, target in renames.items():
            if os.path.exists(os.path.join(temp_dir, source)):
                os.rename(os.path.join(temp_dir, source), os.path.join(temp_dir, target))

        # gerber + drill files as plain folder
        self.step(75, 'Gerberdaten kopieren')
        shutil.copytree(temp_dir_gerber, os.path.join(temp_dir, gerberFolder))

        if self.options.get(SCHEMATIC_PDF_OPT):
            self.step(78, 'Schaltplan-PDF exportieren (kicad-cli)')
            schematic_file = os.path.splitext(board_file)[0] + '.kicad_sch'
            try:
                export_schematic_pdf(schematic_file, os.path.join(temp_dir, name + '_Schaltplan.pdf'),
                                     variables={'ZEICHNUNGSNUMMER': self.options[DRAWING_NO_OPT].strip(),
                                                'INDEX': self.options[INDEX_OPT].strip()},
                                     logger=self.log)
            except Exception as e:
                self.error('Fehler beim Schaltplan-PDF', str(e))

        if self.options.get(PCB_SPEC_OPT):
            self._write_spec(temp_dir, board_file, name)

        self.step(85, 'Dateien in den Freigabeordner kopieren')
        shutil.copytree(temp_dir, release_path)

        # project backup at release time (Freigaben/ itself is excluded)
        if self.options.get(PROJECT_BACKUP_OPT):
            self.step(90, 'Projekt-Backup erstellen')
            try:
                backup_path = os.path.join(release_path, name + '_Projekt-Backup.zip')
                count = backup_project(project_directory, backup_path)
                self.log.info('Projekt-Backup: %s (%d Dateien, %.1f MB)', backup_path, count, os.path.getsize(backup_path) / 1e6)

                # same backup next to KiCad's automatic backups, so the release history is visible there
                history_path = os.path.join(get_kicad_backups_path(board_file), get_kicad_backup_name(name, datetime.datetime.now()))
                os.makedirs(os.path.dirname(history_path), exist_ok=True)
                shutil.copy2(backup_path, history_path)
                self.log.info('Backup-Historie: %s', history_path)
            except Exception as e:
                self.log.error(traceback.format_exc())
                self.error('Fehler beim Projekt-Backup', str(e))

        return release_path

    def _write_spec(self, temp_dir, board_file, name):
        '''PCB specification (Leiterplattenspezifikation)'''
        try:
            values = spec.defaults()
            values.update(self.options.get(PCB_SPEC_VALUES) or {})
            # the stackup of the saved board is authoritative (Board Setup -> Physical Stackup)
            stackup = read_stackup(board_file)
            self.log.info('Lagenaufbau: %s', stackup)
            values.update(stackup)

            header = {
                'projekt': values.get('projekt', ''),
                'leiterplatte': os.path.basename(board_file),
                'firma': values.get('firma', ''),
                'freigabedatum': datetime.datetime.now().strftime('%d.%m.%Y'),
                'freigegeben_von': values.get('freigegeben_von', ''),
                'zeichnungsnummer': self.options[DRAWING_NO_OPT].strip(),
                'index': self.options[INDEX_OPT].strip(),
            }

            views = []
            render_dir = None
            if self.options.get(PCB_SPEC_VIEWS_OPT):
                self.step(80, 'Ansicht Ober-/Unterseite rendern (kicad-cli)')
                render_dir = tempfile.mkdtemp()
                try:
                    for side, caption in (('top', 'ANSICHT OBERSEITE (TOP)'), ('bottom', 'ANSICHT UNTERSEITE (BOTTOM)')):
                        views.append((caption, render_board(board_file, os.path.join(render_dir, side + '.png'), side, logger=self.log)))
                except Exception as e:
                    # the specification is still created, just without images
                    self.log.error(traceback.format_exc())
                    self.error('Fehler bei den Platinenansichten', str(e))
                    views = []

            self.step(83, 'Leiterplattenspezifikation erstellen')
            write_spec_pdf(os.path.join(temp_dir, name + '_Leiterplattenspezifikation.pdf'), header,
                           spec.build_sections(values), values.get('bemerkungen', ''),
                           os.path.join(os.path.dirname(__file__), 'logo_pdf.jpg'), views)
            if render_dir:
                shutil.rmtree(render_dir, ignore_errors=True)
        except Exception as e:
            self.log.error(traceback.format_exc())
            self.error('Fehler bei der Leiterplattenspezifikation', str(e))

    def progress(self, percent):
        if self.wx is None:
            if not self.nonInteractive:
                print_cli_progress_bar(percent, prefix = 'Fortschritt:', suffix = 'fertig', length = 50)
        else:
            wx.PostEvent(self.wx, StatusEvent(percent))
