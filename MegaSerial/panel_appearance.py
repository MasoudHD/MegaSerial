"""Validated per-panel presentation overrides, without Qt dependencies."""
import re

COLOR_KEYS = ('background', 'text', 'title', 'rx', 'tx')


def normalize_appearance(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in COLOR_KEYS:
        color = value.get(key)
        if isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            result[key] = color.lower()
    for key in ('show_ts', 'show_linenum', 'show_counter'):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    return result


def panel_options(global_options, appearance):
    options = {**global_options, 'unicode_text': True}
    for key in ('show_ts', 'show_linenum'):
        if key in appearance:
            options[key] = appearance[key]
    if 'text' in appearance:
        options['colors'] = {key: color if key in ('timestamp', 'delay') else appearance['text']
                             for key, color in global_options['colors'].items()}
    options['direction_colors'] = {key: appearance[key] for key in ('rx', 'tx') if key in appearance}
    return options
