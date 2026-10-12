import os
import wx
import pcbnew  # type: ignore

from .thread import ProcessThread
from .events import StatusEvent
from .options import AUTO_FILL_OPT, AUTO_TRANSLATE_OPT, EXCLUDE_DNP_OPT, EXTEND_EDGE_CUT_OPT, ALTERNATIVE_EDGE_CUT_OPT, EXTRA_LAYERS, ALL_ACTIVE_LAYERS_OPT, ARCHIVE_NAME, OPEN_BROWSER_OPT, BACKUP_OPT, INDEX_OPT, SET_REVISION_OPT, STEP_EXPORT_OPT, DRAWING_NO_OPT, SCHEMATIC_PDF_OPT, PROJECT_BACKUP_OPT, OVERWRITE_RELEASE_OPT
from .archive import normalize_name, get_release_name, get_release_path
from .utils import load_user_options, save_user_options, get_layer_names, save_board
from .debuglog import get_logger
from .process import ProcessManager


# WX GUI form that show the plugin progress
class KiCadToJLCForm(wx.Frame):
    def __init__(self):
        wx.Dialog.__init__(
            self,
            None,
            id=wx.ID_ANY,
            title=u"Schienle_PCB_Freigabe",
            pos=wx.DefaultPosition,
            size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE)

        # self.app = wx.PySimpleApp()
        icon = wx.Icon(os.path.join(os.path.dirname(__file__), 'icon.png'))
        self.SetIcon(icon)
        self.SetBackgroundColour(wx.LIGHT_GREY)

        self.SetSizeHints(wx.Size(600, 100), wx.DefaultSize)

        userOptions = load_user_options({
            EXTRA_LAYERS: "",
            ALL_ACTIVE_LAYERS_OPT: False,
            ARCHIVE_NAME: "",
            EXTEND_EDGE_CUT_OPT: False,
            ALTERNATIVE_EDGE_CUT_OPT: False,
            AUTO_TRANSLATE_OPT: True,
            AUTO_FILL_OPT: True,
            EXCLUDE_DNP_OPT: False,
            OPEN_BROWSER_OPT: True,
            BACKUP_OPT: True,
            DRAWING_NO_OPT: "",
            INDEX_OPT: "",
            SET_REVISION_OPT: True,
            STEP_EXPORT_OPT: True,
            SCHEMATIC_PDF_OPT: True,
            PROJECT_BACKUP_OPT: True,
        })

        logo = wx.Image(os.path.join(os.path.dirname(__file__), 'logo.png'), wx.BITMAP_TYPE_PNG)
        self.mLogo = wx.StaticBitmap(self, bitmap=wx.Bitmap(logo))

        self.mIndexLabel = wx.StaticText(self, label='Release (Freigabe) - drawing number + index:')
        self.mDrawingNoControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mDrawingNoControl.Hint = "Drawing number (Zeichnungsnummer)"
        self.mDrawingNoControl.SetValue(userOptions[DRAWING_NO_OPT])
        self.mIndexControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mIndexControl.Hint = "Index (e.g. A, B, 01)"
        self.mIndexControl.SetValue(userOptions[INDEX_OPT] or pcbnew.GetBoard().GetTitleBlock().GetRevision())
        self.mSetRevisionCheckbox = wx.CheckBox(self, label='Write index to title block revision')
        self.mSetRevisionCheckbox.SetValue(userOptions[SET_REVISION_OPT])
        self.mStepExportCheckbox = wx.CheckBox(self, label='Export 3D model (STEP)')
        self.mStepExportCheckbox.SetValue(userOptions[STEP_EXPORT_OPT])
        self.mSchematicPdfCheckbox = wx.CheckBox(self, label='Export schematic as PDF')
        self.mSchematicPdfCheckbox.SetValue(userOptions[SCHEMATIC_PDF_OPT])
        self.mProjectBackupCheckbox = wx.CheckBox(self, label='Create project backup')
        self.mProjectBackupCheckbox.SetValue(userOptions[PROJECT_BACKUP_OPT])
        self.mReleaseControls = [self.mIndexLabel, self.mDrawingNoControl, self.mIndexControl, self.mSetRevisionCheckbox,
                                 self.mStepExportCheckbox, self.mSchematicPdfCheckbox, self.mProjectBackupCheckbox]


        layers = get_layer_names(pcbnew.GetBoard())
        self.mAdditionalLayersControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mAdditionalLayersControl.Hint = "Additional layers (comma-separated) [optional]"
        self.mAdditionalLayersControl.AutoComplete(layers)
        self.mAdditionalLayersControl.Enable()
        self.mAdditionalLayersControl.SetValue(userOptions[EXTRA_LAYERS])
        self.mArchiveNameControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mArchiveNameControl.Hint = "Archive name (e.g. ${TITLE}_${REVISION}) [optional]"
        self.mArchiveNameControl.Enable()
        self.mArchiveNameControl.SetValue(userOptions[ARCHIVE_NAME])
        self.mAllActiveLayersCheckbox = wx.CheckBox(self, label='Plot all active layers')
        self.mAllActiveLayersCheckbox.SetValue(userOptions[ALL_ACTIVE_LAYERS_OPT])
        self.mExtendEdgeCutsCheckbox = wx.CheckBox(self, label='Set User.1 as V-Cut layer')
        self.mExtendEdgeCutsCheckbox.SetValue(userOptions[EXTEND_EDGE_CUT_OPT])
        self.mAlternativeEdgeCutsCheckbox = wx.CheckBox(self, label='Set User.2 as alternative Edge-Cut layer')
        self.mAlternativeEdgeCutsCheckbox.SetValue(userOptions[ALTERNATIVE_EDGE_CUT_OPT])
        self.mAutomaticTranslationCheckbox = wx.CheckBox(self, label='Apply automatic component translations')
        self.mAutomaticTranslationCheckbox.SetValue(userOptions[AUTO_TRANSLATE_OPT])
        self.mAutomaticFillCheckbox = wx.CheckBox(self, label='Apply automatic fill for all zones')
        self.mAutomaticFillCheckbox.SetValue(userOptions[AUTO_FILL_OPT])
        self.mExcludeDnpCheckbox = wx.CheckBox(self, label='Exclude DNP components from BOM')
        self.mExcludeDnpCheckbox.SetValue(userOptions[EXCLUDE_DNP_OPT])
        self.mOpenBrowserCheckbox = wx.CheckBox(self, label='Open browser after generation')
        self.mOpenBrowserCheckbox.SetValue(userOptions[OPEN_BROWSER_OPT])

        self.mGaugeStatus = wx.Gauge(
            self, wx.ID_ANY, 100, wx.DefaultPosition, wx.Size(600, 20), wx.GA_HORIZONTAL)
        self.mGaugeStatus.SetValue(0)
        self.mGaugeStatus.Hide()

        self.mStatusText = wx.StaticText(self, label='', size=wx.Size(600, -1))
        self.mStatusText.Hide()

        self.mGenerateButton = wx.Button(self, label='Generate', size=wx.Size(600, 60))
        self.mGenerateButton.Bind(wx.EVT_BUTTON, self.onGenerateButtonClick)

        boxSizer = wx.BoxSizer(wx.VERTICAL)

        boxSizer.Add(self.mLogo, 0, wx.ALL, 10)
        for control in self.mReleaseControls:
            boxSizer.Add(control, 0, wx.ALL, 5)
        boxSizer.Add(self.mArchiveNameControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAdditionalLayersControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAllActiveLayersCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExtendEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAlternativeEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticTranslationCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticFillCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExcludeDnpCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mOpenBrowserCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mGaugeStatus, 0, wx.ALL, 5)
        boxSizer.Add(self.mStatusText, 0, wx.ALL, 5)
        boxSizer.Add(self.mGenerateButton, 0, wx.ALL, 5)

        self.SetSizer(boxSizer)
        self.Layout()
        boxSizer.Fit(self)

        self.Centre(wx.BOTH)

        # Bind the ESC key event to a handler
        self.Bind(wx.EVT_CHAR_HOOK, self.onKey)

    # Close the dialog when pressing the ESC key
    def onKey(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close(True)
        else:
            event.Skip()

    def onGenerateButtonClick(self, event):
        options = dict()
        options[DRAWING_NO_OPT] = self.mDrawingNoControl.GetValue().strip()
        options[INDEX_OPT] = self.mIndexControl.GetValue().strip()
        options[SET_REVISION_OPT] = self.mSetRevisionCheckbox.GetValue()
        options[STEP_EXPORT_OPT] = self.mStepExportCheckbox.GetValue()
        options[SCHEMATIC_PDF_OPT] = self.mSchematicPdfCheckbox.GetValue()
        options[PROJECT_BACKUP_OPT] = self.mProjectBackupCheckbox.GetValue()
        options[ARCHIVE_NAME] = self.mArchiveNameControl.GetValue()
        options[EXTRA_LAYERS] = self.mAdditionalLayersControl.GetValue()
        options[ALL_ACTIVE_LAYERS_OPT] = self.mAllActiveLayersCheckbox.GetValue()
        options[EXTEND_EDGE_CUT_OPT] = self.mExtendEdgeCutsCheckbox.GetValue()
        options[ALTERNATIVE_EDGE_CUT_OPT] = self.mAlternativeEdgeCutsCheckbox.GetValue()
        options[AUTO_TRANSLATE_OPT] = self.mAutomaticTranslationCheckbox.GetValue()
        options[AUTO_FILL_OPT] = self.mAutomaticFillCheckbox.GetValue()
        options[EXCLUDE_DNP_OPT] = self.mExcludeDnpCheckbox.GetValue()
        options[OPEN_BROWSER_OPT] = self.mOpenBrowserCheckbox.GetValue()
        options[BACKUP_OPT] = False  # replaced by the project backup of a release

        # a release needs both; without them the original Fabrication Toolkit output is created
        has_drawing_no = bool(normalize_name(options[DRAWING_NO_OPT]))
        has_index = bool(normalize_name(options[INDEX_OPT]))
        if has_drawing_no != has_index:
            wx.MessageBox("For a release please enter both drawing number and index.", "Schienle_PCB_Freigabe", wx.OK | wx.ICON_WARNING)
            (self.mIndexControl if has_drawing_no else self.mDrawingNoControl).SetFocus()
            return

        options[OVERWRITE_RELEASE_OPT] = False
        if has_drawing_no and has_index:
            release_path = get_release_path(pcbnew.GetBoard().GetFileName(), options[DRAWING_NO_OPT], options[INDEX_OPT])
            if os.path.exists(release_path):
                answer = wx.MessageBox("Release '{}' already exists:\n{}\n\nOverwrite it?".format(get_release_name(options[DRAWING_NO_OPT], options[INDEX_OPT]), release_path),
                                       "Schienle_PCB_Freigabe", wx.YES_NO | wx.ICON_QUESTION)
                if answer != wx.YES:
                    return
                options[OVERWRITE_RELEASE_OPT] = True

        save_user_options({k: v for k, v in options.items() if k != OVERWRITE_RELEASE_OPT})

        for control in self.mReleaseControls:
            control.Hide()
        self.mArchiveNameControl.Hide()
        self.mAdditionalLayersControl.Hide()
        self.mAllActiveLayersCheckbox.Hide()
        self.mExtendEdgeCutsCheckbox.Hide()
        self.mAlternativeEdgeCutsCheckbox.Hide()
        self.mAutomaticTranslationCheckbox.Hide()
        self.mAutomaticFillCheckbox.Hide()
        self.mExcludeDnpCheckbox.Hide()
        self.mOpenBrowserCheckbox.Hide()
        self.mGenerateButton.Hide()
        self.mGaugeStatus.Show()
        self.mStatusText.Show()

        # Release: DRC, STEP and PDF are created by kicad-cli from the saved files, so fill the
        # zones, write the index and save the board first. Board changes must happen in the
        # GUI thread, not in the background thread.
        if has_drawing_no and has_index:
            board = pcbnew.GetBoard()
            log = get_logger(os.path.dirname(board.GetFileName()))
            try:
                if options[AUTO_FILL_OPT]:
                    self.setStatusText('Filling zones')
                    log.info('Filling zones')
                    ProcessManager(board).update_zone_fills()
                if options[SET_REVISION_OPT]:
                    log.info('Writing index %s to title block', options[INDEX_OPT])
                    board.GetTitleBlock().SetRevision(options[INDEX_OPT])
                log.info('Saving board')
                save_board(board)
            except Exception as e:
                log.exception('Preparing the board failed')
                wx.MessageBox("Preparing the board failed:\n{}".format(e), "Schienle_PCB_Freigabe", wx.OK | wx.ICON_ERROR)
                self.Destroy()
                return

        self.Fit()
        self.SetTitle('Schienle_PCB_Freigabe (Processing...)')

        StatusEvent.invoke(self, self.updateDisplay)
        ProcessThread(self, options, openBrowser=options[OPEN_BROWSER_OPT])

    def setStatusText(self, text):
        self.mStatusText.SetLabel(text)
        self.SetTitle('Schienle_PCB_Freigabe - ' + text)

    def updateDisplay(self, status):
        if status.data == -1:
            self.SetTitle('Schienle_PCB_Freigabe (Done!)')
            pcbnew.Refresh()
            self.Destroy()
        else:
            self.mGaugeStatus.SetValue(int(status.data))


# Plugin definition
class Plugin(pcbnew.ActionPlugin):
    def __init__(self):
        self.name = "Schienle_PCB_Freigabe"
        self.category = "Manufacturing"
        self.description = "PCB-Freigabe: Fertigungsdaten erstellen, Index setzen und Projekt archivieren"
        self.pcbnew_icon_support = hasattr(self, "show_toolbar_button")
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.dark_icon_file_name = os.path.join(os.path.dirname(__file__), 'icon_dark.png')

    def Run(self):
        KiCadToJLCForm().Show()
