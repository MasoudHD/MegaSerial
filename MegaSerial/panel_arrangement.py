"""Display placement only; routing IDs and event storage are independent."""
from math import ceil, sqrt


def normalize_positions(value, workspace):
    if not isinstance(value, dict):
        return {}
    result, occupied = {}, set()
    for ident, cell in value.items():
        if (ident not in workspace.titles() or not isinstance(cell, list) or len(cell) != 2
                or any(type(n) is not int for n in cell)
                or not 0 <= cell[0] < len(workspace.row_counts)
                or not 0 <= cell[1] < workspace.max_columns or tuple(cell) in occupied):
            continue
        result[ident] = list(cell)
        occupied.add(tuple(cell))
    return result


def default_positions(workspace):
    if workspace.automatic:
        ids = [i for i in workspace.titles() if workspace.is_visible(i)]
        columns = max(1, min(workspace.max_columns, ceil(sqrt(len(ids)))))
        return {ident: [i // columns, i % columns] for i, ident in enumerate(ids)}
    result = {}
    panels = iter(workspace.panels)
    for row, count in enumerate(workspace.row_counts):
        for column in range(count):
            result[next(panels)['id']] = [row, column]
    return result


def positions(workspace):
    if not workspace.display_positions:
        return default_positions(workspace)
    result = {i: list(cell) for i, cell in workspace.display_positions.items()}
    occupied = {tuple(cell) for cell in result.values()}
    available = iter([r, c] for r in range(len(workspace.row_counts))
                     for c in range(workspace.max_columns) if (r, c) not in occupied)
    for ident in workspace.titles():
        if ident not in result and (not workspace.automatic or workspace.is_visible(ident)):
            result[ident] = next(available)
    workspace.display_positions = result
    return result


def move_panel(workspace, ident, row, column):
    if (ident not in workspace.titles() or not workspace.is_visible(ident)
            or type(row) is not int or type(column) is not int
            or not 0 <= row < len(workspace.row_counts)
            or not 0 <= column < workspace.max_columns):
        return False
    current = positions(workspace)
    target = [row, column]
    origin = current[ident]
    if origin == target:
        return False
    occupant = next((i for i, cell in current.items() if cell == target), None)
    if occupant is not None:
        current[occupant] = origin
    current[ident] = target
    workspace.display_positions = current
    return True
