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
from .archive import archive_project, normalize_index, get_index_folder_name
from .step import export_step, stepFileName
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

        _, temp_file = tempfile.mkstemp()
        board_file = self.process_manager.board.GetFileName()
        project_directory = os.path.dirname(board_file)
        index = normalize_index(self.options.get(INDEX_OPT))

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
            self.step(60, 'Generating positions file')
            self.process_manager.generate_positions(temp_dir)

            # generate BOM file
            self.step(70, 'Generating BOM')
            self.process_manager.generate_bom(temp_dir)

            # export 3D model (uses the saved board file, see README)
            if self.options.get(STEP_EXPORT_OPT):
                self.step(75, 'Exporting STEP (kicad-cli, may take a few minutes)')
                try:
                    export_step(board_file, os.path.join(temp_dir, stepFileName), logger=self.log)
                except Exception as e:
                    self.error('STEP export error', str(e))

            # generate production archive
            self.step(85, 'Creating gerber archive')
            temp_file = self.process_manager.generate_archive(temp_dir_gerber, temp_file)
            shutil.move(temp_file, temp_dir)
            shutil.rmtree(temp_dir_gerber)
            temp_file = os.path.join(temp_dir, os.path.basename(temp_file))
        except Exception as e:
            self.log.error(traceback.format_exc())
            self.error('Error', str(e))
            self.progress(100 if self.wx is None else -1)
            return

        self.step(88, 'Copying files to output folder')

        # (the former "progress bar done animation" posted one GUI event per 10 bytes of the
        # gerber archive, which floods the wx event queue on larger boards and freezes KiCad)
        self.log.info('Gerber archive size: %.1f MB', os.path.getsize(temp_file) / 1e6)

        # generate gerber name
        title_block = self.process_manager.board.GetTitleBlock()
        title = title_block.GetTitle()
        revision = title_block.GetRevision()
        company = title_block.GetCompany()
        file_date = title_block.GetDate()

        if (hasattr(self.process_manager.board, "GetProject") and hasattr(pcbnew, "ExpandTextVars")):
            project = self.process_manager.board.GetProject()
            title = pcbnew.ExpandTextVars(title, project)
            revision = pcbnew.ExpandTextVars(revision, project)
            company = pcbnew.ExpandTextVars(company, project)
            file_date = pcbnew.ExpandTextVars(file_date, project)

        # make output dir
        filename = os.path.splitext(os.path.basename(self.process_manager.board.GetFileName()))[0]
        output_path = os.path.join(project_directory, outputFolder)
        if index:
            output_path = os.path.join(output_path, get_index_folder_name(index))
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
        # rename gerber archive
        if self.options[ARCHIVE_NAME]:
            baseName = self.expandTextVariables(self.options[ARCHIVE_NAME])
        elif index:
            baseName = "{} {}".format(title or filename, get_index_folder_name(index))
        else:
            baseName = "{} {}".format(title or filename, revision or '')

        gerberArchiveName = ProcessManager.normalize_filename("_".join((baseName.strip() + '.zip').split()))
        os.rename(temp_file, os.path.join(temp_dir, gerberArchiveName))

        if os.path.exists(os.path.join(temp_dir, stepFileName)):
            os.rename(os.path.join(temp_dir, stepFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '.step').split()))))

        if self.options[ARCHIVE_NAME]:
            if os.path.exists(os.path.join(temp_dir, designatorsFileName)):
                os.rename(os.path.join(temp_dir, designatorsFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_designators.csv').split()))))
            if os.path.exists(os.path.join(temp_dir, placementFileName)):
                os.rename(os.path.join(temp_dir, placementFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_positions.csv').split()))))
            if os.path.exists(os.path.join(temp_dir, bomFileName)):
                os.rename(os.path.join(temp_dir, bomFileName), os.path.join(temp_dir, ProcessManager.normalize_filename("_".join((baseName.strip() + '_bom.csv').split()))))

        # Make a backup as long as the BACKUP_OPT flag is set.
        if self.options[BACKUP_OPT]:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
            backup_name = ProcessManager.normalize_filename("_".join(("{} {}".format(baseName, timestamp).strip()).split()))
            shutil.make_archive(os.path.join(output_path, 'backups', backup_name), 'zip', temp_dir)

        # copy to & open output dir
        try:
            shutil.copytree(temp_dir, output_path, dirs_exist_ok=True)
            if self.openBrowser:
                webbrowser.open("file://%s" % (output_path))
            shutil.rmtree(temp_dir)
        except Exception as e:
            if self.openBrowser:
                webbrowser.open("file://%s" % (temp_dir))

        # archive the complete project (incl. the production data of this index)
        if index and self.options.get(ARCHIVE_PROJECT_OPT):
            self.step(98, 'Archiving project')
            try:
                archive_path = archive_project(board_file, index, outputFolder, overwrite=self.options.get(OVERWRITE_ARCHIVE_OPT, False))
                self.log.info('Project archive: %s (%.1f MB)', archive_path, os.path.getsize(archive_path) / 1e6)
            except Exception as e:
                self.log.error(traceback.format_exc())
                self.error('Archive error', str(e))

        self.step(99, 'Done, output: %s' % output_path)

        if self.wx is None: 
            self.progress(100)
        else:
            self.progress(-1)

    def progress(self, percent):
        if self.wx is None:
            if not self.nonInteractive:
                print_cli_progress_bar(percent, prefix = 'Progress:', suffix = 'Complete', length = 50)
        else:
            wx.PostEvent(self.wx, StatusEvent(percent))
