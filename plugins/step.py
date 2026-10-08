import os
import sys
import shutil
import subprocess

stepFileName = 'board.step'


def _pcbnew_location():
    try:
        import pcbnew  # type: ignore
        return pcbnew.__file__
    except Exception:
        return None


def _macos_bundle_candidates(paths):
    '''Returns <bundle>.app/Contents/MacOS/kicad-cli for every .app bundle found in the given paths.'''
    candidates = []
    for path in paths:
        if not path:
            continue
        path = os.path.realpath(path)
        while path and path != os.path.dirname(path):
            if path.endswith('.app'):
                candidates.append(os.path.join(path, 'Contents', 'MacOS', 'kicad-cli'))
            path = os.path.dirname(path)
    return candidates


def find_kicad_cli():
    '''Locates the kicad-cli executable of the running KiCad installation (KiCad 7+).'''
    exe = 'kicad-cli.exe' if sys.platform == 'win32' else 'kicad-cli'
    candidates = [
        # Windows: KiCad's bundled python.exe lives next to kicad-cli.exe in KiCad\<ver>\bin
        os.path.join(os.path.dirname(sys.executable), exe),
    ]

    # macOS: python and pcbnew run from inside the KiCad.app bundle, wherever it is installed
    candidates += _macos_bundle_candidates([sys.executable, _pcbnew_location()])
    candidates += [
        '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli',
        os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which(exe)
    if found:
        return found

    raise FileNotFoundError('kicad-cli was not found. STEP export requires KiCad 7 or newer.')


def export_step(board_file, output_file, timeout=600, logger=None):
    '''Exports the 3D model of the (saved) board file as STEP using kicad-cli.'''
    cmd = [find_kicad_cli(), 'pcb', 'export', 'step',
           '--subst-models',
           '--output', output_file,
           board_file]

    if logger:
        logger.info('Running: %s', subprocess.list2cmdline(cmd))

    kwargs = {}
    if sys.platform == 'win32':
        kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, errors='replace', timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as e:
        if logger:
            logger.error('kicad-cli timed out after %d s, output so far:\n%s', timeout, e.output)
        raise RuntimeError('STEP export did not finish within {} s.'.format(timeout))

    if logger:
        logger.info('kicad-cli exit code %d, output:\n%s', result.returncode, (result.stdout or '').strip())

    if result.returncode != 0 or not os.path.isfile(output_file):
        raise RuntimeError('STEP export failed (exit code {}):\n{}'.format(result.returncode, (result.stdout or '').strip()[-2000:]))

    return output_file
