"""Safe ANSI SGR color rendering for panel payloads, not terminal emulation."""
import html
import re

SGR = re.compile(r"\x1b\[([0-9;]*)m")
BASIC = ('#000000', '#aa0000', '#00aa00', '#aaaa00', '#0000aa', '#aa00aa', '#00aaaa', '#aaaaaa',
         '#555555', '#ff5555', '#55ff55', '#ffff55', '#5555ff', '#ff55ff', '#55ffff', '#ffffff')


def plain_ansi(text):
    return SGR.sub('', text)


def indexed_color(index):
    if not 0 <= index <= 255:
        return None
    if index < 16:
        return BASIC[index]
    if index >= 232:
        gray = 8 + 10 * (index - 232)
        return f'#{gray:02x}{gray:02x}{gray:02x}'
    n = index - 16
    levels = (0, 95, 135, 175, 215, 255)
    return '#%02x%02x%02x' % (levels[n // 36], levels[(n // 6) % 6], levels[n % 6])


def ansi_html(text):
    style = {}
    parts = []
    pos = 0

    def append(value):
        escaped = html.escape(value).replace('\n', '<br>')
        css = ';'.join(f'{k}:{v}' for k, v in style.items())
        parts.append(f'<span style="{css}">{escaped}</span>' if css else escaped)

    for match in SGR.finditer(text):
        append(text[pos:match.start()])
        codes = [int(v or '0') if len(v) <= 3 else -1 for v in match.group(1).split(';')]
        i = 0
        while i < len(codes):
            code = codes[i]
            if code == 0:
                style.clear()
            elif code == 1:
                style['font-weight'] = 'bold'
            elif code == 22:
                style.pop('font-weight', None)
            elif code in (39, 49):
                style.pop('color' if code == 39 else 'background-color', None)
            elif 30 <= code <= 37 or 90 <= code <= 97:
                style['color'] = BASIC[code - 30 if code < 90 else code - 90 + 8]
            elif 40 <= code <= 47 or 100 <= code <= 107:
                style['background-color'] = BASIC[code - 40 if code < 100 else code - 100 + 8]
            elif code in (38, 48) and i + 1 < len(codes):
                key = 'color' if code == 38 else 'background-color'
                mode = codes[i + 1]
                if mode == 5 and i + 2 < len(codes):
                    color = indexed_color(codes[i + 2])
                    if color:
                        style[key] = color
                    i += 2
                elif mode == 2 and i + 4 < len(codes):
                    rgb = codes[i + 2:i + 5]
                    if all(0 <= n <= 255 for n in rgb):
                        style[key] = '#%02x%02x%02x' % tuple(rgb)
                    i += 4
            i += 1
        pos = match.end()
    append(text[pos:])
    return ''.join(parts)
