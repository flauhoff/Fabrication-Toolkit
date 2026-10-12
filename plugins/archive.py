import os
import re
import shutil
import tempfile
import zipfile

from .debuglog import logFileName

# All releases are created in <project>/Freigaben/<drawing number>_<index>/
releaseFolder = 'Freigaben'
gerberFolder = 'Gerberdaten'

# Files and folders that never belong into a project backup
excludedDirNames = {'.git', '.svn', '.hg', '__pycache__', '.history'}
excludedTopLevelDirNames = {releaseFolder, 'production', 'archive'}
excludedFileNames = {'fp-info-cache', '.DS_Store', 'Thumbs.db', logFileName}
excludedFileSuffixes = ('.lck', '.pyc', '.bak')
excludedFilePrefixes = ('_autosave-', '~')


def normalize_name(value):
    '''Turns a user supplied drawing number / index (e.g. "4711-02", "A") into a filename safe token.'''
    value = (value or '').strip()
    value = re.sub(r'[^\w\s\.\-]', '', value)
    return '_'.join(value.split())


def get_release_name(drawing_number, index):
    '''e.g. ("4711-02", "B") -> "4711-02_B"'''
    return '{}_{}'.format(normalize_name(drawing_number), normalize_name(index))


def get_kicad_backups_path(board_file):
    '''KiCad's automatic backup folder: <project dir>/<project name>-backups'''
    project_directory = os.path.dirname(os.path.abspath(board_file))
    projects = [f for f in os.listdir(project_directory) if f.endswith('.kicad_pro')]
    if len(projects) == 1:
        project_name = os.path.splitext(projects[0])[0]
    else:
        project_name = os.path.splitext(os.path.basename(board_file))[0]
    return os.path.join(project_directory, project_name + '-backups')


def get_kicad_backup_name(release_name, timestamp):
    '''
    Name of the release backup in KiCad's backup folder. It deliberately does not follow KiCad's
    "<project>-YYYY-MM-DD_HHMMSS.zip" pattern, so KiCad's backup retention never deletes it.
    '''
    return 'Freigabe_{}_{}.zip'.format(release_name, timestamp.strftime('%Y-%m-%d_%H%M%S'))


def get_release_path(board_file, drawing_number, index):
    project_directory = os.path.dirname(os.path.abspath(board_file))
    return os.path.join(project_directory, releaseFolder, get_release_name(drawing_number, index))


def _is_excluded_dir(rel_dir, name):
    if name in excludedDirNames or name.endswith('-backups'):
        return True
    if rel_dir == '.' and name in excludedTopLevelDirNames:
        return True
    return False


def _is_excluded_file(name):
    if name in excludedFileNames:
        return True
    return name.endswith(excludedFileSuffixes) or name.startswith(excludedFilePrefixes)


def backup_project(project_directory, archive_path):
    '''
    Zips the complete KiCad project directory (schematics, board, libraries, 3D models, ...)
    into archive_path. Releases, old production outputs, backups, lock files and VCS folders
    are left out. Returns the number of archived files.
    '''
    project_directory = os.path.abspath(project_directory)
    os.makedirs(os.path.dirname(os.path.abspath(archive_path)), exist_ok=True)

    # Write to a temporary file first, so that a failed run never leaves a broken archive behind
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    count = 0

    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(project_directory):
                rel_dir = os.path.relpath(root, project_directory)
                dirs[:] = sorted(d for d in dirs if not _is_excluded_dir(rel_dir, d))

                for name in sorted(files):
                    if _is_excluded_file(name):
                        continue
                    zf.write(os.path.join(root, name), os.path.normpath(os.path.join(rel_dir, name)))
                    count += 1

        shutil.move(temp_path, archive_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return count
