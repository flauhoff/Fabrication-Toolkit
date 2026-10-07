import os
import sys
import logging
import platform

logFileName = 'schienle-pcb-freigabe.log'
loggerName = 'schienle_pcb_freigabe'


def get_logger(project_directory=None):
    '''
    Returns the plugin logger. When a project directory is given, all messages are
    (additionally) written to <project>/schienle-pcb-freigabe.log, so that hangs and
    errors of the background thread can be analysed afterwards.
    '''
    logger = logging.getLogger(loggerName)
    logger.setLevel(logging.DEBUG)

    if project_directory:
        path = os.path.abspath(os.path.join(project_directory, logFileName))
        if not any(getattr(h, 'baseFilename', None) == path for h in logger.handlers):
            # only one log file at a time (the current project)
            for h in [h for h in logger.handlers if isinstance(h, logging.FileHandler)]:
                logger.removeHandler(h)
                h.close()
            try:
                handler = logging.FileHandler(path, mode='a', encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s [%(threadName)s] %(levelname)s: %(message)s'))
                logger.addHandler(handler)
            except Exception:
                pass

    return logger


def log_environment(logger):
    try:
        import pcbnew  # type: ignore
        version = pcbnew.GetBuildVersion()
    except Exception:
        version = 'unknown'
    logger.info('KiCad %s | Python %s | %s | executable %s', version, sys.version.split()[0], platform.platform(), sys.executable)
