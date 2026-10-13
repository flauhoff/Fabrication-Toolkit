import os
import wx
import pcbnew  # type: ignore

from .thread import ProcessThread, TITLE
from .events import StatusEvent
from .options import *
from . import spec
from .archive import normalize_name, get_release_name, get_release_path
from .projectinfo import read_stackup, read_schematic_revision
from .utils import load_user_options, save_user_options, get_layer_names, save_board, set_revision, get_project_variable
from .debuglog import get_logger
from .process import ProcessManager

READ_ONLY_COLOUR = wx.Colour(235, 235, 235)
HINT_COLOUR = wx.Colour(90, 90, 90)
RED = wx.Colour(231, 50, 56)


def _read_only(control, tooltip):
    control.SetEditable(False)
    control.SetBackgroundColour(READ_ONLY_COLOUR)
    control.SetToolTip(tooltip)


# Release dialog
class ReleaseForm(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(
            self,
            None,
            id=wx.ID_ANY,
            title=TITLE,
            pos=wx.DefaultPosition,
            size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE)

        icon = wx.Icon(os.path.join(os.path.dirname(__file__), 'icon.png'))
        self.SetIcon(icon)
        self.SetBackgroundColour(wx.LIGHT_GREY)
        self.SetSizeHints(wx.Size(600, 100), wx.DefaultSize)

        board = pcbnew.GetBoard()
        userOptions = load_user_options({
            DRAWING_NO_OPT: "",
            INDEX_OPT: "",
            SET_REVISION_OPT: True,
            STEP_EXPORT_OPT: True,
            SCHEMATIC_PDF_OPT: True,
            PCB_SPEC_OPT: True,
            PCB_SPEC_VIEWS_OPT: True,
            PCB_SPEC_VALUES: {},
            PROJECT_BACKUP_OPT: True,
            OPEN_BROWSER_OPT: True,
            AUTO_FILL_OPT: True,
            AUTO_TRANSLATE_OPT: True,
            EXCLUDE_DNP_OPT: False,
            EXTRA_LAYERS: "",
            ALL_ACTIVE_LAYERS_OPT: False,
            EXTEND_EDGE_CUT_OPT: False,
            ALTERNATIVE_EDGE_CUT_OPT: False,
        })

        logo = wx.Image(os.path.join(os.path.dirname(__file__), 'logo.png'), wx.BITMAP_TYPE_PNG)
        self.mLogo = wx.StaticBitmap(self, bitmap=wx.Bitmap(logo))

        self.mNotebook = wx.Notebook(self)
        self.createReleasePage(board, userOptions)
        self.mSpecControls = self.createSpecPage(board, userOptions[PCB_SPEC_VALUES])

        self.mGaugeStatus = wx.Gauge(self, wx.ID_ANY, 100, wx.DefaultPosition, wx.Size(600, 20), wx.GA_HORIZONTAL)
        self.mGaugeStatus.SetValue(0)
        self.mGaugeStatus.Hide()

        self.mStatusText = wx.StaticText(self, label='', size=wx.Size(600, -1))
        self.mStatusText.Hide()

        self.mGenerateButton = wx.Button(self, label='Freigabe erstellen', size=wx.Size(600, 50))
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

        # Close the dialog when pressing the ESC key
        self.Bind(wx.EVT_CHAR_HOOK, self.onKey)

    def createReleasePage(self, board, userOptions):
        '''First tab: drawing number, index and what the release contains.'''
        page = wx.Panel(self.mNotebook)
        self.mNotebook.AddPage(page, 'Freigabe')
        sizer = wx.BoxSizer(wx.VERTICAL)

        # drawing number is entered manually; the index comes from the project text variable INDEX, if defined
        index_var = get_project_variable(board, 'INDEX')

        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
        grid.AddGrowableCol(1)
        self.mDrawingNoControl = wx.TextCtrl(page, value=userOptions[DRAWING_NO_OPT])
        self.mIndexControl = wx.TextCtrl(page, value=index_var or userOptions[INDEX_OPT] or board.GetTitleBlock().GetRevision())
        self.mIndexControl.SetHint('z. B. A, B, 01')
        if index_var is not None:
            _read_only(self.mIndexControl, 'Aus der Projekt-Textvariable INDEX (Datei → Board Setup → Text Variables)')
        grid.Add(wx.StaticText(page, label='Zeichnungsnummer'), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.mDrawingNoControl, 1, wx.EXPAND)
        grid.Add(wx.StaticText(page, label='Index'), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.mIndexControl, 1, wx.EXPAND)
        sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 10)

        if index_var is None:
            hint = wx.StaticText(page, label='Tipp: INDEX als Projekt-Textvariable anlegen und in den Schriftfeldern '
                                             '${INDEX} verwenden – dann zeigen Schaltplan und Platine immer denselben '
                                             'Index und er wird hier automatisch übernommen.')
            hint.SetForegroundColour(HINT_COLOUR)
            hint.Wrap(570)
            sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        def checkbox(label, key, indent=8):
            control = wx.CheckBox(page, label=label)
            control.SetValue(userOptions[key])
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.AddSpacer(indent)
            row.Add(control)
            sizer.Add(row, 0, wx.RIGHT | wx.BOTTOM, 8)
            return control

        self.mSetRevisionCheckbox = checkbox('Index in die Revision des Platinen-Schriftfelds schreiben', SET_REVISION_OPT)
        self.mAutomaticFillCheckbox = checkbox('Alle Zonen vor der Freigabe füllen', AUTO_FILL_OPT)
        self.mStepExportCheckbox = checkbox('3D-Modell exportieren (STEP)', STEP_EXPORT_OPT)
        self.mSchematicPdfCheckbox = checkbox('Schaltplan als PDF exportieren', SCHEMATIC_PDF_OPT)
        self.mPcbSpecCheckbox = checkbox('Leiterplattenspezifikation erstellen (PDF)', PCB_SPEC_OPT)
        self.mPcbSpecViewsCheckbox = checkbox('mit Ansicht Ober- und Unterseite', PCB_SPEC_VIEWS_OPT, indent=32)
        self.mPcbSpecViewsCheckbox.Enable(userOptions[PCB_SPEC_OPT])
        self.mPcbSpecCheckbox.Bind(wx.EVT_CHECKBOX, lambda e: self.mPcbSpecViewsCheckbox.Enable(self.mPcbSpecCheckbox.GetValue()))
        self.mProjectBackupCheckbox = checkbox('Projekt-Backup erstellen', PROJECT_BACKUP_OPT)
        self.mOpenBrowserCheckbox = checkbox('Freigabeordner danach öffnen', OPEN_BROWSER_OPT)

        # fabrication data options from the original Fabrication Toolkit (JLCPCB oriented)
        self.mAdvancedPane = wx.CollapsiblePane(page, label='Erweitert (Fertigungsdaten)')
        self.mAdvancedPane.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.onAdvancedToggled)
        pane = self.mAdvancedPane.GetPane()
        paneSizer = wx.BoxSizer(wx.VERTICAL)

        self.mAdditionalLayersControl = wx.TextCtrl(pane, value=userOptions[EXTRA_LAYERS] or '')
        self.mAdditionalLayersControl.SetHint('Zusätzliche Lagen für die Gerberdaten (kommagetrennt)')
        self.mAdditionalLayersControl.AutoComplete(get_layer_names(board))
        paneSizer.Add(self.mAdditionalLayersControl, 0, wx.ALL | wx.EXPAND, 5)

        def pane_checkbox(label, key):
            control = wx.CheckBox(pane, label=label)
            control.SetValue(userOptions[key])
            paneSizer.Add(control, 0, wx.ALL, 5)
            return control

        self.mAllActiveLayersCheckbox = pane_checkbox('Alle aktiven Lagen plotten', ALL_ACTIVE_LAYERS_OPT)
        self.mExtendEdgeCutsCheckbox = pane_checkbox('User.1 als V-Cut-Lage (Ritzlinien) verwenden', EXTEND_EDGE_CUT_OPT)
        self.mAlternativeEdgeCutsCheckbox = pane_checkbox('User.2 als alternative Kontur (statt Edge.Cuts) verwenden', ALTERNATIVE_EDGE_CUT_OPT)
        self.mAutomaticTranslationCheckbox = pane_checkbox('JLC-Bestückungskorrekturen (Rotation/Position) anwenden', AUTO_TRANSLATE_OPT)
        self.mExcludeDnpCheckbox = pane_checkbox('DNP-Bauteile aus der Stückliste ausschließen', EXCLUDE_DNP_OPT)
        pane.SetSizer(paneSizer)

        sizer.Add(self.mAdvancedPane, 0, wx.ALL | wx.EXPAND, 5)
        page.SetSizer(sizer)

    def createSpecPage(self, board, stored):
        '''Second tab: the PCB specification form. Returns {key: control}.'''
        page = wx.ScrolledWindow(self.mNotebook)
        page.SetScrollRate(0, 10)
        page.SetMinSize(wx.Size(-1, 520))
        self.mNotebook.AddPage(page, 'Leiterplattenspezifikation')

        try:
            stackup = read_stackup(board.GetFileName())
        except Exception:
            stackup = {}

        values = spec.defaults()
        values.update(spec.board_values(board))
        values.update({k: v for k, v in (stored or {}).items() if k not in spec.BOARD_KEYS and v})
        values.update(stackup)

        controls = {}
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)
        grid.AddGrowableCol(1)

        def heading(text):
            label = wx.StaticText(page, label=text)
            label.SetFont(label.GetFont().Bold())
            label.SetForegroundColour(RED)
            grid.Add(label, 0, wx.TOP, 10)
            grid.Add((0, 0))

        def row(key, text, control):
            grid.Add(wx.StaticText(page, label=text), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
            controls[key] = control

        heading('KOPF')
        for key, text in spec.HEADER_FIELDS:
            if key == 'firma':
                # two lines in the PDF header; Enter sets the line break
                control = wx.TextCtrl(page, value=values.get(key, ''), style=wx.TE_MULTILINE, size=wx.Size(-1, 48))
            else:
                control = wx.TextCtrl(page, value=values.get(key, ''))
            row(key, text, control)

        for title, fields in spec.SECTIONS:
            heading(title)
            for key, text, choices, _ in fields:
                if choices is spec.AUTO:
                    control = wx.TextCtrl(page, value=values.get(key, ''))
                    _read_only(control, 'Aus der Platine')
                elif key in stackup:
                    control = wx.TextCtrl(page, value=values.get(key, ''))
                    _read_only(control, 'Aus dem Lagenaufbau (Board Setup → Physical Stackup)')
                else:
                    control = wx.ComboBox(page, value=values.get(key, ''), choices=choices, style=wx.CB_DROPDOWN)
                row(key, text, control)

        heading('BEMERKUNGEN')
        remarks = wx.TextCtrl(page, value=values.get('bemerkungen', ''), style=wx.TE_MULTILINE, size=wx.Size(-1, 80))
        controls['bemerkungen'] = remarks

        hint = wx.StaticText(page, label='Grau hinterlegte Werte kommen aus der Platine bzw. aus dem Lagenaufbau '
                                         '(Board Setup → Physical Stackup) und werden dort geändert.')
        hint.SetForegroundColour(HINT_COLOUR)
        hint.Wrap(560)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(remarks, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)
        page.SetSizer(sizer)
        return controls

    def onAdvancedToggled(self, event):
        page = self.mNotebook.GetPage(0)
        page.Layout()
        page.Fit()
        self.mNotebook.Fit()
        self.Layout()
        self.Fit()

    def onKey(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close(True)
        else:
            event.Skip()

    def onGenerateButtonClick(self, event):
        board = pcbnew.GetBoard()

        options = dict()
        options[DRAWING_NO_OPT] = self.mDrawingNoControl.GetValue().strip()
        options[INDEX_OPT] = self.mIndexControl.GetValue().strip()
        options[SET_REVISION_OPT] = self.mSetRevisionCheckbox.GetValue()
        options[AUTO_FILL_OPT] = self.mAutomaticFillCheckbox.GetValue()
        options[STEP_EXPORT_OPT] = self.mStepExportCheckbox.GetValue()
        options[SCHEMATIC_PDF_OPT] = self.mSchematicPdfCheckbox.GetValue()
        options[PCB_SPEC_OPT] = self.mPcbSpecCheckbox.GetValue()
        options[PCB_SPEC_VIEWS_OPT] = self.mPcbSpecViewsCheckbox.GetValue()
        options[PCB_SPEC_VALUES] = {key: control.GetValue() if key == 'bemerkungen' else control.GetValue().strip()
                                    for key, control in self.mSpecControls.items()}
        options[PROJECT_BACKUP_OPT] = self.mProjectBackupCheckbox.GetValue()
        options[OPEN_BROWSER_OPT] = self.mOpenBrowserCheckbox.GetValue()
        options[EXTRA_LAYERS] = self.mAdditionalLayersControl.GetValue()
        options[ALL_ACTIVE_LAYERS_OPT] = self.mAllActiveLayersCheckbox.GetValue()
        options[EXTEND_EDGE_CUT_OPT] = self.mExtendEdgeCutsCheckbox.GetValue()
        options[ALTERNATIVE_EDGE_CUT_OPT] = self.mAlternativeEdgeCutsCheckbox.GetValue()
        options[AUTO_TRANSLATE_OPT] = self.mAutomaticTranslationCheckbox.GetValue()
        options[EXCLUDE_DNP_OPT] = self.mExcludeDnpCheckbox.GetValue()

        if not normalize_name(options[DRAWING_NO_OPT]) or not normalize_name(options[INDEX_OPT]):
            wx.MessageBox('Bitte Zeichnungsnummer und Index eingeben.', TITLE, wx.OK | wx.ICON_WARNING)
            self.mNotebook.SetSelection(0)
            (self.mIndexControl if normalize_name(options[DRAWING_NO_OPT]) else self.mDrawingNoControl).SetFocus()
            return

        if options[PCB_SPEC_OPT] and not options[PCB_SPEC_VALUES].get('freigegeben_von'):
            wx.MessageBox("Bitte in der Leiterplattenspezifikation 'Freigegeben von' ausfüllen.", TITLE, wx.OK | wx.ICON_WARNING)
            self.mNotebook.SetSelection(1)
            self.mSpecControls['freigegeben_von'].SetFocus()
            return

        # the schematic title block should show the same index (checked on the saved schematic)
        schematic_revision = read_schematic_revision(os.path.splitext(board.GetFileName())[0] + '.kicad_sch')
        if schematic_revision is not None and schematic_revision != options[INDEX_OPT] and '${INDEX}' not in schematic_revision:
            answer = wx.MessageBox("Die Revision im Schaltplan-Schriftfeld ist '{}', der Index der Freigabe ist '{}'.\n\n"
                                   "Tipp: Im Schaltplan-Schriftfeld ${{INDEX}} als Revision eintragen (mit der "
                                   "Projekt-Textvariable INDEX) – dann passt es immer.\n\n"
                                   "Trotzdem freigeben?".format(schematic_revision, options[INDEX_OPT]),
                                   TITLE, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            if answer != wx.YES:
                return

        options[OVERWRITE_RELEASE_OPT] = False
        release_path = get_release_path(board.GetFileName(), options[DRAWING_NO_OPT], options[INDEX_OPT])
        if os.path.exists(release_path):
            answer = wx.MessageBox("Die Freigabe '{}' existiert bereits:\n{}\n\nÜberschreiben?".format(
                                       get_release_name(options[DRAWING_NO_OPT], options[INDEX_OPT]), release_path),
                                   TITLE, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
            if answer != wx.YES:
                return
            options[OVERWRITE_RELEASE_OPT] = True

        save_user_options({k: v for k, v in options.items() if k != OVERWRITE_RELEASE_OPT})

        self.mNotebook.Hide()
        self.mGenerateButton.Hide()
        self.mGaugeStatus.Show()
        self.mStatusText.Show()

        # DRC, STEP, PDFs and images are created by kicad-cli from the saved files, so fill the zones,
        # write the index and save the board first. Board changes must happen in the GUI thread.
        log = get_logger(os.path.dirname(board.GetFileName()))
        try:
            if options[AUTO_FILL_OPT]:
                self.setStatusText('Zonen füllen')
                log.info('Zonen füllen')
                ProcessManager(board).update_zone_fills()
            if options[SET_REVISION_OPT]:
                if set_revision(board, options[INDEX_OPT]):
                    log.info('Index %s in das Schriftfeld geschrieben', options[INDEX_OPT])
                else:
                    log.info('Revision im Schriftfeld verweist auf eine Textvariable und bleibt unverändert')
            log.info('Platine speichern')
            save_board(board)
        except Exception as e:
            log.exception('Vorbereiten der Platine fehlgeschlagen')
            wx.MessageBox("Die Platine konnte nicht vorbereitet werden:\n{}".format(e), TITLE, wx.OK | wx.ICON_ERROR)
            self.Destroy()
            return

        self.Fit()
        self.SetTitle(TITLE + ' (läuft ...)')

        StatusEvent.invoke(self, self.updateDisplay)
        ProcessThread(self, options, openBrowser=options[OPEN_BROWSER_OPT])

    def setStatusText(self, text):
        self.mStatusText.SetLabel(text)
        self.SetTitle(TITLE + ' - ' + text)

    def updateDisplay(self, status):
        if status.data == -1:
            self.SetTitle(TITLE + ' (fertig)')
            pcbnew.Refresh()
            self.Destroy()
        else:
            self.mGaugeStatus.SetValue(int(status.data))


# Plugin definition
class Plugin(pcbnew.ActionPlugin):
    def __init__(self):
        self.name = "Schienle_PCB_Freigabe"
        self.category = "Manufacturing"
        self.description = "PCB-Freigabe: DRC, Fertigungsdaten, Schaltplan, Leiterplattenspezifikation und Backup mit Zeichnungsnummer und Index"
        self.pcbnew_icon_support = hasattr(self, "show_toolbar_button")
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.dark_icon_file_name = os.path.join(os.path.dirname(__file__), 'icon_dark.png')

    def Run(self):
        ReleaseForm().Show()
