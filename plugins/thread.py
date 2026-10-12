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
from .kicad_cli import export_step, export_schematic_pdf, stepFileName
from .config import *
from .options import *
from .utils import print_cli_progress_bar, save_board
from .debuglog import get_logger, log_environment


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
                logging.error("Schienle_PCB_Freigabe - Error" + str(e))
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
            self.log.info('  ... done in %.1f s', now - self._step_started[1])
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
            logging.error("Schienle_PCB_Freigabe - %s: %s", title, message)
        else:
            wx.CallAfter(wx.MessageBox, message, "Schienle_PCB_Freigabe - " + title, wx.OK | wx.ICON_ERROR)

    def expandTextVariables(self, string):
        board = self.board if self.board is not None else pcbnew.GetBoard()
        titleBlock = board.GetTitleBlock()

        titleBlockVars = {
            "ISSUE_DATE": titleBlock.GetDate(),
            "CURRENT_DATE": datetime.datetime.now().strftime('%Y-%m-%d'),
            "REVISION": titleBlock.GetRevision(),
            "TITLE": titleBlock.GetTitle(),
            "COMPANY": titleBlock.GetCompany(),
            "INDEX": self.options.get(INDEX_OPT) or "",
            "ZEICHNUNGSNUMMER": self.options.get(DRAWING_NO_OPT) or "",
        }

        for comment_index in range(9):
            titleBlockVars[f"COMMENT{comment_index + 1}"] = titleBlock.GetComment(comment_index)

        for var, val in titleBlockVars.items():
            string = string.replace(f"${{{var}}}", val)

        if (hasattr(self.process_manager.board, "GetProject") and hasattr(pcbnew, "ExpandTextVars")):
            project = self.process_manager.board.GetProject()
            string = pcbnew.ExpandTextVars(string, project)

        return string


    def run(self):
        self.log.info('=' * 70)
        log_environment(self.log)
        self.log.info('Board: %s', self.process_manager.board.GetFileName())
        self.log.info('Options: %s', self.options)
        try:
            self._run()
        except Exception:
            # never die silently in the background thread
            self.log.error('Unhandled error:\n%s', traceback.format_exc())
            self.error('Error', traceback.format_exc(limit=3))
            self.progress(100 if self.wx is None else -1)
        self.log.info('Finished')

    def _run(self):
        # initializing
        self.step(0, 'Preparing')

        temp_dir = tempfile.mkdtemp()
        temp_dir_gerber = temp_dir + "_g"
        os.makedirs(temp_dir_gerber)

        board_file = self.process_manager.board.GetFileName()
        project_directory = os.path.dirname(board_file)
        drawing_number = normalize_name(self.options.get(DRAWING_NO_OPT))
        index = normalize_name(self.options.get(INDEX_OPT))
        release = bool(drawing_number and index)

        try:
            # Write the index into the title block (revision) before plotting, so that
            # ${REVISION} on the board (e.g. silkscreen) already shows the new index
            # (in the GUI this is done by the dialog in the main thread, see plugin.py)
            if index and self.options.get(SET_REVISION_OPT) and self.wx is None:
                self.step(5, 'Writing index to title block and saving board')
                self.process_manager.board.GetTitleBlock().SetRevision(self.options[INDEX_OPT].strip())
                save_board(self.process_manager.board)

            # Verify all zones are up-to-date
            if (self.options[AUTO_FILL_OPT]):
                self.step(10, 'Filling zones')
                self.process_manager.update_zone_fills()

            # generate gerber
            self.step(20, 'Generating gerber files')
            self.process_manager.generate_gerber(temp_dir_gerber, self.options[EXTRA_LAYERS], self.options[EXTEND_EDGE_CUT_OPT],
                                                 self.options[ALTERNATIVE_EDGE_CUT_OPT], self.options[ALL_ACTIVE_LAYERS_OPT])

            # generate drill file
            self.step(30, 'Generating drill files')
            self.process_manager.generate_drills(temp_dir_gerber)

            # generate netlist
            self.step(40, 'Generating netlist')
            self.process_manager.generate_netlist(temp_dir)

            # generate data tables
            self.step(50, 'Collecting components')
            self.process_manager.generate_tables(temp_dir, self.options[AUTO_TRANSLATE_OPT], self.options[EXCLUDE_DNP_OPT])

            # generate pick and place file
            self.step(55, 'Generating positions file')
            self.process_manager.generate_positions(temp_dir)

            # generate BOM file
            self.step(60, 'Generating BOM')
            self.process_manager.generate_bom(temp_dir)

            # export 3D model (uses the saved board file, see README)
            if self.options.get(STEP_EXPORT_OPT):
                self.step(65, 'Exporting STEP (kicad-cli, may take a few minutes)')
                try:
                    export_step(board_file, os.path.join(temp_dir, stepFileName), logger=self.log)
                except Exception as e:
                    self.error('STEP export error', str(e))

            if release:
                output_path = self._finish_release(temp_dir, temp_dir_gerber, board_file, project_directory, drawing_number, index)
            else:
                output_path = self._finish_default(temp_dir, temp_dir_gerber, project_directory)
        except Exception as e:
            self.log.error(traceback.format_exc())
            self.error('Error', str(e))
            self.progress(100 if self.wx is None else -1)
            return
        finally:
            for path in (temp_dir, temp_dir_gerber):
                shutil.rmtree(path, ignore_errors=True)

        self.step(99, 'Done, output: %s' % output_path)
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
                <name>_Schaltplan.pdf
                <name>_Projekt-Backup.zip
        '''
        name = get_release_name(drawing_number, index)
        release_path = get_release_path(board_file, drawing_number, index)
        self.log.info('Release: %s', release_path)

        if os.path.exists(release_path):
            if not self.options.get(OVERWRITE_RELEASE_OPT):
                raise FileExistsError('Release "{}" already exists:\n{}'.format(name, release_path))
            self.log.info('Overwriting existing release')
            shutil.rmtree(release_path)

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
        self.step(75, 'Copying gerber files')
        shutil.copytree(temp_dir_gerber, os.path.join(temp_dir, gerberFolder))

        # schematic PDF
        if self.options.get(SCHEMATIC_PDF_OPT):
            self.step(80, 'Exporting schematic PDF (kicad-cli)')
            schematic_file = os.path.splitext(board_file)[0] + '.kicad_sch'
            try:
                export_schematic_pdf(schematic_file, os.path.join(temp_dir, name + '_Schaltplan.pdf'),
                                     variables={'ZEICHNUNGSNUMMER': self.options[DRAWING_NO_OPT].strip(),
                                                'INDEX': self.options[INDEX_OPT].strip()},
                                     logger=self.log)
            except Exception as e:
                self.error('Schematic PDF error', str(e))

        self.step(85, 'Copying files to release folder')
        shutil.copytree(temp_dir, release_path)

        # project backup at release time (Freigaben/ itself is excluded)
        if self.options.get(PROJECT_BACKUP_OPT):
            self.step(90, 'Creating project backup')
            try:
                backup_path = os.path.join(release_path, name + '_Projekt-Backup.zip')
                count = backup_project(project_directory, backup_path)
                self.log.info('Project backup: %s (%d files, %.1f MB)', backup_path, count, os.path.getsize(backup_path) / 1e6)
            except Exception as e:
                self.log.error(traceback.format_exc())
                self.error('Project backup error', str(e))

        return release_path

    def _finish_default(self, temp_dir, temp_dir_gerber, project_directory):
        '''Original Fabrication Toolkit behaviour: everything goes to production/, gerbers zipped.'''
        self.step(80, 'Creating gerber archive')
        _, temp_file = tempfile.mkstemp()
        temp_file = self.process_manager.generate_archive(temp_dir_gerber, temp_file)
        temp_file = shutil.move(temp_file, temp_dir)

        title_block = self.process_manager.board.GetTitleBlock()
        title = title_block.GetTitle()
        revision = title_block.GetRevision()
        if (hasattr(self.process_manager.board, "GetProject") and hasattr(pcbnew, "ExpandTextVars")):
            project = self.process_manager.board.GetProject()
            title = pcbnew.ExpandTextVars(title, project)
            revision = pcbnew.ExpandTextVars(revision, project)

        filename = os.path.splitext(os.path.basename(self.process_manager.board.GetFileName()))[0]
        output_path = os.path.join(project_directory, outputFolder)
        os.makedirs(output_path, exist_ok=True)

        if self.options[ARCHIVE_NAME]:
            baseName = self.expandTextVariables(self.options[ARCHIVE_NAME])
        else:
            baseName = "{} {}".format(title or filename, revision or '')

        def target(suffix):
            return os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + suffix).split())))

        os.rename(temp_file, target('.zip'))
        if os.path.exists(os.path.join(temp_dir, stepFileName)):
            os.rename(os.path.join(temp_dir, stepFileName), target('.step'))

        if self.options[ARCHIVE_NAME]:
            for source, suffix in ((designatorsFileName, '_designators.csv'), (placementFileName, '_positions.csv'), (bomFileName, '_bom.csv')):
                if os.path.exists(os.path.join(temp_dir, source)):
                    os.rename(os.path.join(temp_dir, source), target(suffix))

        # Make a backup as long as the BACKUP_OPT flag is set.
        if self.options[BACKUP_OPT]:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
            backup_name = ProcessManager.normalize_filename("_".join(("{} {}".format(baseName, timestamp).strip()).split()))
            shutil.make_archive(os.path.join(output_path, 'backups', backup_name), 'zip', temp_dir)

        self.step(90, 'Copying files to output folder')
        shutil.copytree(temp_dir, output_path, dirs_exist_ok=True)
        return output_path

    def progress(self, percent):
        if self.wx is None:
            if not self.nonInteractive:
                print_cli_progress_bar(percent, prefix = 'Progress:', suffix = 'Complete', length = 50)
        else:
            wx.PostEvent(self.wx, StatusEvent(percent))
