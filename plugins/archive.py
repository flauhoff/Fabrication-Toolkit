import os
import re
import shutil
import tempfile
import zipfile

archiveFolder = 'archive'

# Files and folders that never belong into a project archive
excludedDirNames = {'.git', '.svn', '.hg', '__pycache__', '.history', archiveFolder}
excludedFileNames = {'fp-info-cache', '.DS_Store', 'Thumbs.db'}
excludedFileSuffixes = ('.lck', '.pyc', '.bak')
excludedFilePrefixes = ('_autosave-', '~')


def normalize_index(index):
    '''Turns a user supplied index (e.g. "A", "01", "Rev 2") into a filename safe token.'''
    index = (index or '').strip()
    index = re.sub(r'[^\w\s\.\-]', '', index)
    return '_'.join(index.split())


def get_index_folder_name(index):
    return 'Index_{}'.format(normalize_index(index))


def get_project_archive_path(board_file, index):
    '''Returns the path of the project archive for the given board file and index.'''
    project_directory = os.path.dirname(os.path.abspath(board_file))
    project_name = os.path.splitext(os.path.basename(board_file))[0]
    archive_name = '{}_{}.zip'.format(project_name, get_index_folder_name(index))
    return os.path.join(project_directory, archiveFolder, archive_name)


def _is_excluded_dir(rel_dir, name, production_folder, index_folder):
    if name in excludedDirNames or name.endswith('-backups'):
        return True

    # Only keep the production data of the archived index
    if rel_dir == '.' and name == production_folder:
        return False
    if rel_dir == production_folder and name != index_folder:
        return True

    return False


def _is_excluded_file(rel_dir, name, production_folder):
    if name in excludedFileNames:
        return True
    if name.endswith(excludedFileSuffixes) or name.startswith(excludedFilePrefixes):
        return True

    # Skip loose files directly inside the production folder (legacy, non-indexed outputs)
    if rel_dir == production_folder:
        return True

    return False


def archive_project(board_file, index, production_folder, overwrite=False):
    '''
    Archives the complete KiCad project (schematics, board, libraries, 3D models, ...) that
    contains the given board file into `<project>/archive/<project>_Index_<index>.zip`.
    The production data of the given index is included, other indices and backups are not.
    Returns the path of the created archive.
    '''
    if not normalize_index(index):
        raise ValueError('An index is required to archive the project.')

    project_directory = os.path.dirname(os.path.abspath(board_file))
    archive_path = get_project_archive_path(board_file, index)
    index_folder = get_index_folder_name(index)

    if os.path.exists(archive_path) and not overwrite:
        raise FileExistsError('Project archive for index "{}" already exists:\n{}'.format(index, archive_path))

    os.makedirs(os.path.dirname(archive_path), exist_ok=True)

    # Write to a temporary file first, so that a failed run never leaves a broken archive behind
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)

    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(project_directory):
                rel_dir = os.path.relpath(root, project_directory)
                dirs[:] = sorted(d for d in dirs if not _is_excluded_dir(rel_dir, d, production_folder, index_folder))

                for name in sorted(files):
                    if _is_excluded_file(rel_dir, name, production_folder):
                        continue
                    path = os.path.join(root, name)
                    zf.write(path, os.path.normpath(os.path.join(rel_dir, name)))

        shutil.move(temp_path, archive_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return archive_path
