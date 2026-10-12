import os
import wx
import pcbnew  # type: ignore

from .thread import ProcessThread
from .events import StatusEvent
from .options import AUTO_FILL_OPT, AUTO_TRANSLATE_OPT, EXCLUDE_DNP_OPT, EXTEND_EDGE_CUT_OPT, ALTERNATIVE_EDGE_CUT_OPT, EXTRA_LAYERS, ALL_ACTIVE_LAYERS_OPT, ARCHIVE_NAME, OPEN_BROWSER_OPT, BACKUP_OPT, INDEX_OPT, SET_REVISION_OPT, STEP_EXPORT_OPT, DRAWING_NO_OPT, SCHEMATIC_PDF_OPT, PROJECT_BACKUP_OPT, OVERWRITE_RELEASE_OPT, PCB_SPEC_OPT, PCB_SPEC_VALUES, PCB_SPEC_VIEWS_OPT
from . import spec
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

        board = pcbnew.GetBoard()
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
            PCB_SPEC_OPT: True,
            PCB_SPEC_VIEWS_OPT: True,
            PCB_SPEC_VALUES: {},
        })

        logo = wx.Image(os.path.join(os.path.dirname(__file__), 'logo.png'), wx.BITMAP_TYPE_PNG)
        self.mLogo = wx.StaticBitmap(self, bitmap=wx.Bitmap(logo))

        self.mNotebook = wx.Notebook(self)
        page = wx.Panel(self.mNotebook)
        self.mNotebook.AddPage(page, 'Freigabe')

        self.mIndexLabel = wx.StaticText(page, label='Release (Freigabe) - drawing number + index:')
        self.mDrawingNoControl = wx.TextCtrl(page, size=wx.Size(600, 50))
        self.mDrawingNoControl.Hint = "Drawing number (Zeichnungsnummer)"
        self.mDrawingNoControl.SetValue(userOptions[DRAWING_NO_OPT])
        self.mIndexControl = wx.TextCtrl(page, size=wx.Size(600, 50))
        self.mIndexControl.Hint = "Index (e.g. A, B, 01)"
        self.mIndexControl.SetValue(userOptions[INDEX_OPT] or board.GetTitleBlock().GetRevision())
        self.mSetRevisionCheckbox = wx.CheckBox(page, label='Write index to title block revision')
        self.mSetRevisionCheckbox.SetValue(userOptions[SET_REVISION_OPT])
        self.mStepExportCheckbox = wx.CheckBox(page, label='Export 3D model (STEP)')
        self.mStepExportCheckbox.SetValue(userOptions[STEP_EXPORT_OPT])
        self.mSchematicPdfCheckbox = wx.CheckBox(page, label='Export schematic as PDF')
        self.mSchematicPdfCheckbox.SetValue(userOptions[SCHEMATIC_PDF_OPT])
        self.mPcbSpecCheckbox = wx.CheckBox(page, label='Create PCB specification (Leiterplattenspezifikation, PDF)')
        self.mPcbSpecCheckbox.SetValue(userOptions[PCB_SPEC_OPT])
        self.mPcbSpecViewsCheckbox = wx.CheckBox(page, label='Add top / bottom view to PCB specification (KiCad 9+)')
        self.mPcbSpecViewsCheckbox.SetValue(userOptions[PCB_SPEC_VIEWS_OPT])
        self.mPcbSpecCheckbox.Bind(wx.EVT_CHECKBOX, lambda e: self.mPcbSpecViewsCheckbox.Enable(self.mPcbSpecCheckbox.GetValue()))
        self.mPcbSpecViewsCheckbox.Enable(userOptions[PCB_SPEC_OPT])
        self.mProjectBackupCheckbox = wx.CheckBox(page, label='Create project backup')
        self.mProjectBackupCheckbox.SetValue(userOptions[PROJECT_BACKUP_OPT])

        layers = get_layer_names(board)
        self.mAdditionalLayersControl = wx.TextCtrl(page, size=wx.Size(600, 50))
        self.mAdditionalLayersControl.Hint = "Additional layers (comma-separated) [optional]"
        self.mAdditionalLayersControl.AutoComplete(layers)
        self.mAdditionalLayersControl.Enable()
        self.mAdditionalLayersControl.SetValue(userOptions[EXTRA_LAYERS])
        self.mArchiveNameControl = wx.TextCtrl(page, size=wx.Size(600, 50))
        self.mArchiveNameControl.Hint = "Archive name (e.g. ${TITLE}_${REVISION}) [optional]"
        self.mArchiveNameControl.Enable()
        self.mArchiveNameControl.SetValue(userOptions[ARCHIVE_NAME])
        self.mAllActiveLayersCheckbox = wx.CheckBox(page, label='Plot all active layers')
        self.mAllActiveLayersCheckbox.SetValue(userOptions[ALL_ACTIVE_LAYERS_OPT])
        self.mExtendEdgeCutsCheckbox = wx.CheckBox(page, label='Set User.1 as V-Cut layer')
        self.mExtendEdgeCutsCheckbox.SetValue(userOptions[EXTEND_EDGE_CUT_OPT])
        self.mAlternativeEdgeCutsCheckbox = wx.CheckBox(page, label='Set User.2 as alternative Edge-Cut layer')
        self.mAlternativeEdgeCutsCheckbox.SetValue(userOptions[ALTERNATIVE_EDGE_CUT_OPT])
        self.mAutomaticTranslationCheckbox = wx.CheckBox(page, label='Apply automatic component translations')
        self.mAutomaticTranslationCheckbox.SetValue(userOptions[AUTO_TRANSLATE_OPT])
        self.mAutomaticFillCheckbox = wx.CheckBox(page, label='Apply automatic fill for all zones')
        self.mAutomaticFillCheckbox.SetValue(userOptions[AUTO_FILL_OPT])
        self.mExcludeDnpCheckbox = wx.CheckBox(page, label='Exclude DNP components from BOM')
        self.mExcludeDnpCheckbox.SetValue(userOptions[EXCLUDE_DNP_OPT])
        self.mOpenBrowserCheckbox = wx.CheckBox(page, label='Open browser after generation')
        self.mOpenBrowserCheckbox.SetValue(userOptions[OPEN_BROWSER_OPT])

        pageSizer = wx.BoxSizer(wx.VERTICAL)
        for control in (self.mIndexLabel, self.mDrawingNoControl, self.mIndexControl, self.mSetRevisionCheckbox,
                        self.mStepExportCheckbox, self.mSchematicPdfCheckbox, self.mPcbSpecCheckbox, self.mPcbSpecViewsCheckbox, self.mProjectBackupCheckbox,
                        self.mArchiveNameControl, self.mAdditionalLayersControl, self.mAllActiveLayersCheckbox,
                        self.mExtendEdgeCutsCheckbox, self.mAlternativeEdgeCutsCheckbox, self.mAutomaticTranslationCheckbox,
                        self.mAutomaticFillCheckbox, self.mExcludeDnpCheckbox, self.mOpenBrowserCheckbox):
            pageSizer.Add(control, 0, wx.ALL, 5)
        page.SetSizer(pageSizer)

        self.mSpecControls = self.createSpecPage(board, userOptions[PCB_SPEC_VALUES])

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
        boxSizer.Add(self.mNotebook, 0, wx.ALL | wx.EXPAND, 5)
        boxSizer.Add(self.mGaugeStatus, 0, wx.ALL, 5)
        boxSizer.Add(self.mStatusText, 0, wx.ALL, 5)
        boxSizer.Add(self.mGenerateButton, 0, wx.ALL, 5)

        self.SetSizer(boxSizer)
        self.Layout()
        boxSizer.Fit(self)

        self.Centre(wx.BOTH)

        # Bind the ESC key event to a handler
        self.Bind(wx.EVT_CHAR_HOOK, self.onKey)

    def createSpecPage(self, board, stored):
        '''Second tab: the PCB specification form. Returns {key: control}.'''
        page = wx.ScrolledWindow(self.mNotebook)
        page.SetScrollRate(0, 10)
        self.mNotebook.AddPage(page, 'Leiterplattenspezifikation')

        values = spec.defaults()
        values.update(spec.board_values(board))
        values.update({k: v for k, v in (stored or {}).items() if k not in spec.BOARD_KEYS and v})

        controls = {}
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)
        grid.AddGrowableCol(1)

        def heading(text):
            label = wx.StaticText(page, label=text)
            label.SetFont(label.GetFont().Bold())
            label.SetForegroundColour(wx.Colour(231, 50, 56))
            grid.Add(label, 0, wx.TOP, 10)
            grid.Add((0, 0))

        def row(key, text, control):
            grid.Add(wx.StaticText(page, label=text), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
            controls[key] = control

        heading('KOPF')
        for key, text in spec.HEADER_FIELDS:
            row(key, text, wx.TextCtrl(page, value=values.get(key, '')))

        for title, fields in spec.SECTIONS:
            heading(title)
            for key, text, choices, _ in fields:
                if choices is spec.AUTO:
                    control = wx.TextCtrl(page, value=values.get(key, ''), style=wx.TE_READONLY)
                    control.SetToolTip('Read from the board')
                    control.SetBackgroundColour(wx.Colour(235, 235, 235))
                else:
                    control = wx.ComboBox(page, value=values.get(key, ''), choices=choices, style=wx.CB_DROPDOWN)
                row(key, text, control)

        heading('BEMERKUNGEN')
        remarks = wx.TextCtrl(page, value=values.get('bemerkungen', ''), style=wx.TE_MULTILINE, size=wx.Size(-1, 80))
        controls['bemerkungen'] = remarks

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(remarks, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)
        page.SetSizer(sizer)
        return controls

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
        options[PCB_SPEC_OPT] = self.mPcbSpecCheckbox.GetValue()
        options[PCB_SPEC_VIEWS_OPT] = self.mPcbSpecViewsCheckbox.GetValue()
        options[PROJECT_BACKUP_OPT] = self.mProjectBackupCheckbox.GetValue()
        options[PCB_SPEC_VALUES] = {key: control.GetValue().strip() if key != 'bemerkungen' else control.GetValue()
                                    for key, control in self.mSpecControls.items()}
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
            self.mNotebook.SetSelection(0)
            (self.mIndexControl if has_drawing_no else self.mDrawingNoControl).SetFocus()
            return

        if has_drawing_no and options[PCB_SPEC_OPT] and not options[PCB_SPEC_VALUES].get('freigegeben_von'):
            wx.MessageBox("Please fill in 'Freigegeben von' in the PCB specification.", "Schienle_PCB_Freigabe", wx.OK | wx.ICON_WARNING)
            self.mNotebook.SetSelection(1)
            self.mSpecControls['freigegeben_von'].SetFocus()
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

        self.mNotebook.Hide()
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
