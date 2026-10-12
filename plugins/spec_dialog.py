import wx

from .spec import FIELDS, load_spec, save_spec, missing_fields


# Form to fill in the PCB specification (Leiterplattenspezifikation) of the project
class SpecDialog(wx.Dialog):
    def __init__(self, parent, board):
        wx.Dialog.__init__(
            self,
            parent,
            id=wx.ID_ANY,
            title=u"Leiterplattenspezifikation",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.board = board
        self.board_file = board.GetFileName()
        spec = load_spec(self.board_file, board)

        self.controls = {}
        grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=10)
        grid.AddGrowableCol(1)

        for key, label, choices, _, required in FIELDS:
            value = spec.get(key, '')

            if choices == 'board':
                control = wx.TextCtrl(self, value=value, size=wx.Size(320, -1), style=wx.TE_READONLY)
                control.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
                control.SetToolTip('Wird bei der Freigabe aus dem Board übernommen')
            elif choices is None and key == 'notes':
                control = wx.TextCtrl(self, value=value, size=wx.Size(320, 80), style=wx.TE_MULTILINE)
            elif choices is None:
                control = wx.TextCtrl(self, value=value, size=wx.Size(320, -1))
            else:
                # editable drop down, so that values not in the list can be entered as well
                control = wx.ComboBox(self, value=value, choices=choices, size=wx.Size(320, -1), style=wx.CB_DROPDOWN)

            self.controls[key] = control
            grid.Add(wx.StaticText(self, label=label + (' *' if required and choices != 'board' else '')), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)

        hint = wx.StaticText(self, label='* Pflichtfeld. Grau hinterlegte Werte werden bei der Freigabe aus dem Board übernommen.')

        buttons = wx.StdDialogButtonSizer()
        save_button = wx.Button(self, wx.ID_OK, label='Speichern')
        save_button.Bind(wx.EVT_BUTTON, self.onSave)
        buttons.AddButton(save_button)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, label='Abbrechen'))
        buttons.Realize()

        box_sizer = wx.BoxSizer(wx.VERTICAL)
        box_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        box_sizer.Add(hint, 0, wx.LEFT | wx.RIGHT, 10)
        box_sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(box_sizer)
        box_sizer.Fit(self)
        self.Centre(wx.BOTH)

    def get_spec(self):
        return {key: control.GetValue().strip() for key, control in self.controls.items()}

    def onSave(self, event):
        spec = self.get_spec()

        missing = missing_fields(spec)
        if missing:
            wx.MessageBox("Bitte folgende Pflichtfelder ausfüllen:\n\n" + "\n".join(missing),
                          "Leiterplattenspezifikation", wx.OK | wx.ICON_WARNING)
            return

        try:
            save_spec(self.board_file, spec)
        except OSError as e:
            wx.MessageBox(str(e), "Leiterplattenspezifikation - Fehler beim Speichern", wx.OK | wx.ICON_ERROR)
            return

        self.EndModal(wx.ID_OK)
