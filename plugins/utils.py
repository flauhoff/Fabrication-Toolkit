import os
import json
from .config import optionsFileName
import wx

def get_user_options_file_path(board):
    return os.path.join(board.project_directory, optionsFileName)

def load_user_options(board, default_options):
    try:
        with open(get_user_options_file_path(board), 'r') as f:
            user_options = json.load(f)
    except:
        user_options = default_options

    # merge the user options with the default options
    options = default_options.copy()
    options.update(user_options)
    return options

def save_user_options(board, options):
    try:
        with open(get_user_options_file_path(board), 'w') as f:
            json.dump(options, f)
    except:
        wx.MessageBox("Error saving user options", "Error", wx.OK | wx.ICON_ERROR)

def get_layer_names(board):
    """Returns a list of the enabled layer names of the current board"""
    return board.layer_names()

def print_cli_progress_bar(percent, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar string
    @params:
        percent     - Required  : current percentage (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    if percent == -1:
        percent = 0
    filledLength = int(length * (percent / 100 ))
    bar = fill * filledLength + '-' * (length - filledLength)
    percent2dec = "%.2f" % percent
    print(f'\r{prefix} |{bar}| {percent2dec}% {suffix}', end = printEnd)
    # Print New Line on Complete
    if percent == 100: 
        print()
def save_board(board):
    """Saves the board in KiCad (kicad-cli works on the saved file)"""
    board.save()

def set_revision(board, index):
    """Writes the index into the board title block revision, unless the revision refers to a
    text variable (e.g. ${INDEX}) - then the project variable is the source and is kept."""
    if '${' in board.title_block().revision:
        return False
    try:
        board.set_revision(index)
    except Exception as e:
        raise RuntimeError('Der Index konnte nicht in das Schriftfeld geschrieben werden (dafür ist KiCad 10.0.1 '
                           'oder neuer nötig). Option abwählen oder KiCad aktualisieren.\n{}'.format(e))
    return True

def get_project_variable(board, name):
    """Value of a project text variable (Board/Schematic Setup -> Text Variables), None if not defined."""
    reference = '${%s}' % name
    value = board.expand_text_variables(reference)
    # KiCad leaves unknown variables unexpanded
    return None if value == reference else value
