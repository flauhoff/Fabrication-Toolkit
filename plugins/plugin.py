import os
import wx
import pcbnew  # type: ignore

from .thread import ProcessThread
from .events import StatusEvent
from .options import AUTO_FILL_OPT, AUTO_TRANSLATE_OPT, EXCLUDE_DNP_OPT, EXTEND_EDGE_CUT_OPT, ALTERNATIVE_EDGE_CUT_OPT, EXTRA_LAYERS, ALL_ACTIVE_LAYERS_OPT, ARCHIVE_NAME, OPEN_BROWSER_OPT, BACKUP_OPT, INDEX_OPT, SET_REVISION_OPT, ARCHIVE_PROJECT_OPT, OVERWRITE_ARCHIVE_OPT
from .archive import normalize_index, get_project_archive_path
from .utils import load_user_options, save_user_options, get_layer_names


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
            INDEX_OPT: "",
            SET_REVISION_OPT: True,
            ARCHIVE_PROJECT_OPT: True,
        })

        self.mIndexLabel = wx.StaticText(self, label='Index:')
        self.mIndexControl = wx.TextCtrl(self, size=wx.Size(600, 50))
        self.mIndexControl.Hint = "Index (e.g. A, B, 01) [required for project archive]"
        self.mIndexControl.SetValue(userOptions[INDEX_OPT] or pcbnew.GetBoard().GetTitleBlock().GetRevision())
        self.mSetRevisionCheckbox = wx.CheckBox(self, label='Write index to title block revision (saves the board)')
        self.mSetRevisionCheckbox.SetValue(userOptions[SET_REVISION_OPT])
        self.mArchiveProjectCheckbox = wx.CheckBox(self, label='Archive project with index')
        self.mArchiveProjectCheckbox.SetValue(userOptions[ARCHIVE_PROJECT_OPT])

        self.mOptionsLabel = wx.StaticText(self, label='Options:')
        # self.mOptionsSeparator = wx.StaticLine(self)

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
        self.mBackupCheckbox = wx.CheckBox(self, label='Generate backup files')
        self.mBackupCheckbox.SetValue(userOptions[BACKUP_OPT])

        self.mGaugeStatus = wx.Gauge(
            self, wx.ID_ANY, 100, wx.DefaultPosition, wx.Size(600, 20), wx.GA_HORIZONTAL)
        self.mGaugeStatus.SetValue(0)
        self.mGaugeStatus.Hide()

        self.mGenerateButton = wx.Button(self, label='Generate', size=wx.Size(600, 60))
        self.mGenerateButton.Bind(wx.EVT_BUTTON, self.onGenerateButtonClick)

        boxSizer = wx.BoxSizer(wx.VERTICAL)

        boxSizer.Add(self.mIndexLabel, 0, wx.ALL, 5)
        boxSizer.Add(self.mIndexControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mSetRevisionCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mArchiveProjectCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mOptionsLabel, 0, wx.ALL, 5)
        # boxSizer.Add(self.mOptionsSeparator, 0, wx.ALL, 5)
        boxSizer.Add(self.mArchiveNameControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAdditionalLayersControl, 0, wx.ALL, 5)
        boxSizer.Add(self.mAllActiveLayersCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExtendEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAlternativeEdgeCutsCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticTranslationCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mAutomaticFillCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mExcludeDnpCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mOpenBrowserCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mBackupCheckbox, 0, wx.ALL, 5)
        boxSizer.Add(self.mGaugeStatus, 0, wx.ALL, 5)
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
        options[INDEX_OPT] = self.mIndexControl.GetValue().strip()
        options[SET_REVISION_OPT] = self.mSetRevisionCheckbox.GetValue()
        options[ARCHIVE_PROJECT_OPT] = self.mArchiveProjectCheckbox.GetValue()
        options[ARCHIVE_NAME] = self.mArchiveNameControl.GetValue()
        options[EXTRA_LAYERS] = self.mAdditionalLayersControl.GetValue()
        options[ALL_ACTIVE_LAYERS_OPT] = self.mAllActiveLayersCheckbox.GetValue()
        options[EXTEND_EDGE_CUT_OPT] = self.mExtendEdgeCutsCheckbox.GetValue()
        options[ALTERNATIVE_EDGE_CUT_OPT] = self.mAlternativeEdgeCutsCheckbox.GetValue()
        options[AUTO_TRANSLATE_OPT] = self.mAutomaticTranslationCheckbox.GetValue()
        options[AUTO_FILL_OPT] = self.mAutomaticFillCheckbox.GetValue()
        options[EXCLUDE_DNP_OPT] = self.mExcludeDnpCheckbox.GetValue()
        options[OPEN_BROWSER_OPT] = self.mOpenBrowserCheckbox.GetValue()
        options[BACKUP_OPT] = self.mBackupCheckbox.GetValue()

        if not normalize_index(options[INDEX_OPT]) and (options[SET_REVISION_OPT] or options[ARCHIVE_PROJECT_OPT]):
            wx.MessageBox("Please enter an index.", "Schienle_PCB_Freigabe", wx.OK | wx.ICON_WARNING)
            self.mIndexControl.SetFocus()
            return

        options[OVERWRITE_ARCHIVE_OPT] = False
        if options[ARCHIVE_PROJECT_OPT]:
            archive_path = get_project_archive_path(pcbnew.GetBoard().GetFileName(), options[INDEX_OPT])
            if os.path.exists(archive_path):
                answer = wx.MessageBox("A project archive for index '{}' already exists:\n{}\n\nOverwrite it?".format(options[INDEX_OPT], archive_path),
                                       "Schienle_PCB_Freigabe", wx.YES_NO | wx.ICON_QUESTION)
                if answer != wx.YES:
                    return
                options[OVERWRITE_ARCHIVE_OPT] = True

        save_user_options({k: v for k, v in options.items() if k != OVERWRITE_ARCHIVE_OPT})

        self.mIndexLabel.Hide()
        self.mIndexControl.Hide()
        self.mSetRevisionCheckbox.Hide()
        self.mArchiveProjectCheckbox.Hide()
        self.mOptionsLabel.Hide()
        self.mArchiveNameControl.Hide()
        self.mAdditionalLayersControl.Hide()
        self.mAllActiveLayersCheckbox.Hide()
        self.mExtendEdgeCutsCheckbox.Hide()
        self.mAlternativeEdgeCutsCheckbox.Hide()
        self.mAutomaticTranslationCheckbox.Hide()
        self.mAutomaticFillCheckbox.Hide()
        self.mExcludeDnpCheckbox.Hide()
        self.mOpenBrowserCheckbox.Hide()
        self.mBackupCheckbox.Hide()
        self.mGenerateButton.Hide()
        self.mGaugeStatus.Show()

        self.Fit()
        self.SetTitle('Schienle_PCB_Freigabe (Processing...)')

        StatusEvent.invoke(self, self.updateDisplay)
        ProcessThread(self, options, openBrowser=options[OPEN_BROWSER_OPT])

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
