import json


def load_drc_report(report_file):
    '''
    Reads a kicad-cli DRC report (--format json) and returns (errors, warnings).
    Every entry is a violation dict ({type, description, severity, items, ...}).
    Excluded violations (marked as excluded in KiCad's DRC dialog) are ignored.
    '''
    with open(report_file, 'r', encoding='utf-8') as f:
        report = json.load(f)

    errors, warnings = [], []
    for section in ('violations', 'unconnected_items', 'schematic_parity'):
        for violation in report.get(section, []):
            if violation.get('excluded'):
                continue
            severity = violation.get('severity', '')
            if severity == 'error':
                errors.append(violation)
            elif severity == 'warning':
                warnings.append(violation)

    return errors, warnings


def format_violation(violation):
    lines = ['[{}] {}'.format(violation.get('type', ''), violation.get('description', ''))]
    for item in violation.get('items', []):
        pos = item.get('pos') or {}
        lines.append('    {} @ ({}, {})'.format(item.get('description', ''), pos.get('x', '?'), pos.get('y', '?')))
    return '\n'.join(lines)


def format_drc_summary(errors, warnings, limit=None):
    '''Human readable DRC summary; `limit` caps the number of listed errors (for message boxes).'''
    text = ['DRC: {} error(s), {} warning(s)'.format(len(errors), len(warnings))]

    for title, entries in (('Errors', errors), ('Warnings', warnings)):
        if not entries:
            continue
        shown = entries if limit is None else entries[:limit]
        text.append('')
        text.append('{}:'.format(title))
        text.extend(format_violation(v) for v in shown)
        if len(shown) < len(entries):
            text.append('    ... and {} more'.format(len(entries) - len(shown)))
        if limit is not None:
            break  # message box: errors only

    return '\n'.join(text)
