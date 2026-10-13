import os
import sys
import shutil
import subprocess
import tempfile

stepFileName = 'board.step'


# kicad-cli of the running KiCad, as reported by the IPC API (see set_kicad_cli_path)
_kicad_cli_path = None


def set_kicad_cli_path(path):
    global _kicad_cli_path
    _kicad_cli_path = path


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
        _kicad_cli_path,
        # Windows: KiCad's bundled python.exe lives next to kicad-cli.exe in KiCad\<ver>\bin
        os.path.join(os.path.dirname(sys.executable), exe),
    ]

    # macOS: python runs from inside the KiCad.app bundle, wherever it is installed
    candidates += _macos_bundle_candidates([sys.executable])
    candidates += [
        '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli',
        os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'),
    ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    found = shutil.which(exe)
    if found:
        return found

    raise FileNotFoundError('kicad-cli was not found.')


def _run(cmd, timeout, logger):
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
        raise RuntimeError('kicad-cli did not finish within {} s.'.format(timeout))

    output = (result.stdout or '').strip()
    if logger:
        logger.info('kicad-cli exit code %d, output:\n%s', result.returncode, output)
    return result.returncode, output


def export_step(board_file, output_file, timeout=600, logger=None):
    '''Exports the 3D model of the (saved) board file as STEP using kicad-cli.'''
    cmd = [find_kicad_cli(), 'pcb', 'export', 'step',
           '--subst-models',
           '--include-tracks',     # tracks and vias
           '--include-pads',
           '--include-zones',
           '--drill-origin',       # origin = drill/place file origin of the board (instead of the board center)
           '--output', output_file,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    if returncode != 0 or not os.path.isfile(output_file):
        raise RuntimeError('STEP export failed (exit code {}):\n{}'.format(returncode, output[-2000:]))

    return output_file


def export_schematic_pdf(schematic_file, output_file, variables=None, timeout=300, logger=None):
    '''
    Plots all sheets of the (saved) schematic into one PDF using kicad-cli.
    `variables` are passed as text variables (e.g. ${INDEX} in the title block, KiCad 8+);
    KiCad 7 does not know --define-var, so the export is retried without them.
    '''
    if not os.path.isfile(schematic_file):
        raise FileNotFoundError('Schematic not found: {}'.format(schematic_file))

    base = [find_kicad_cli(), 'sch', 'export', 'pdf', '--output', output_file]
    defines = []
    for key, value in (variables or {}).items():
        defines += ['--define-var', '{}={}'.format(key, value)]

    returncode, output = _run(base + defines + [schematic_file], timeout, logger)
    if returncode != 0 and defines:
        if logger:
            logger.info('Retrying schematic export without --define-var (KiCad 7)')
        returncode, output = _run(base + [schematic_file], timeout, logger)

    if returncode != 0 or not os.path.isfile(output_file):
        raise RuntimeError('Schematic PDF export failed (exit code {}):\n{}'.format(returncode, output[-2000:]))

    return output_file


def run_drc(board_file, report_file, timeout=600, logger=None):
    '''
    Runs the design rule check on the (saved) board file and writes a JSON report (KiCad 8+).
    The exit code is not used to detect violations; the caller evaluates the report.
    '''
    cmd = [find_kicad_cli(), 'pcb', 'drc',
           '--format', 'json',
           '--units', 'mm',
           '--severity-all',
           '--output', report_file,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    if returncode != 0 or not os.path.isfile(report_file):
        raise RuntimeError('DRC could not be run (exit code {}). The DRC check requires KiCad 8 or newer.\n{}'.format(returncode, output[-2000:]))

    return report_file


def render_board(board_file, output_file, side='top', width=1600, height=1200, timeout=600, logger=None):
    '''Renders the (saved) board in 3D as PNG with transparent background (KiCad 9+).'''
    cmd = [find_kicad_cli(), 'pcb', 'render',
           '--side', side,
           '--background', 'transparent',
           '--quality', 'basic',
           '--width', str(width),
           '--height', str(height),
           '--output', output_file,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    if returncode != 0 or not os.path.isfile(output_file):
        raise RuntimeError('Rendering the {} view failed (exit code {}). Board images require KiCad 9 or newer.\n{}'.format(side, returncode, output[-2000:]))

    return output_file


def _check(returncode, output, output_path, what):
    if returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError('{} failed (exit code {}):\n{}'.format(what, returncode, output[-2000:]))


def export_gerbers(board_file, output_dir, layers, timeout=600, logger=None):
    '''Plots one gerber file per layer (KiCad standard layer names, e.g. F.Cu) into output_dir.'''
    cmd = [find_kicad_cli(), 'pcb', 'export', 'gerbers',
           '--layers', ','.join(layers),
           '--no-x2',
           '--subtract-soldermask',
           '--use-drill-file-origin',
           '--output', output_dir,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    _check(returncode, output, output_dir, 'Gerber export')

    # the gerber job file is not part of the fabrication data
    for name in os.listdir(output_dir):
        if name.endswith('.gbrjob'):
            os.remove(os.path.join(output_dir, name))


def export_gerber(board_file, output_file, layers, timeout=600, logger=None):
    '''Plots the given layers together into one gerber file (e.g. Edge.Cuts with the V-cut layer).'''
    temp_dir = tempfile.mkdtemp()
    try:
        cmd = [find_kicad_cli(), 'pcb', 'export', 'gerbers',
               '--layers', layers[0],
               '--no-x2',
               '--subtract-soldermask',
               '--use-drill-file-origin',
               '--output', temp_dir,
               board_file]
        if len(layers) > 1:
            cmd[-1:-1] = ['--common-layers', ','.join(layers[1:])]

        returncode, output = _run(cmd, timeout, logger)
        plots = [name for name in os.listdir(temp_dir) if not name.endswith('.gbrjob')]
        if returncode != 0 or len(plots) != 1:
            raise RuntimeError('Gerber export failed (exit code {}):\n{}'.format(returncode, output[-2000:]))
        shutil.move(os.path.join(temp_dir, plots[0]), output_file)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def export_drill(board_file, output_dir, timeout=600, logger=None):
    '''Excellon drill files (separate PTH / NPTH, mm, drill/place file origin) with gerber drill maps.'''
    cmd = [find_kicad_cli(), 'pcb', 'export', 'drill',
           '--format', 'excellon',
           '--excellon-units', 'mm',
           '--drill-origin', 'plot',
           '--excellon-separate-th',
           '--excellon-oval-format', 'route',
           '--generate-map',
           '--map-format', 'gerberx2',
           '--output', output_dir if output_dir.endswith(os.sep) else output_dir + os.sep,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    _check(returncode, output, output_dir, 'Drill export')


def export_ipcd356(board_file, output_file, timeout=600, logger=None):
    '''IPC-D-356 netlist (KiCad 9+).'''
    cmd = [find_kicad_cli(), 'pcb', 'export', 'ipcd356',
           '--output', output_file,
           board_file]

    returncode, output = _run(cmd, timeout, logger)
    _check(returncode, output, output_file, 'IPC-D-356 netlist export')
