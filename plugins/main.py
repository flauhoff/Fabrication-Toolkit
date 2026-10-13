'''
Entry point of the toolbar button, started by KiCad in the plugin's Python environment (see plugin.json).
Imports this directory as package, so the modules can keep their relative imports.
'''
import os
import sys
import importlib.util

PACKAGE = 'schienle_pcb_freigabe'


def load_package():
    directory = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(PACKAGE, os.path.join(directory, '__init__.py'),
                                                  submodule_search_locations=[directory])
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = package
    spec.loader.exec_module(package)
    return package


if __name__ == '__main__':
    load_package()
    importlib.import_module(PACKAGE + '.plugin').run()
