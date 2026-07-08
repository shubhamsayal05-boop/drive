"""Bridge DriveScope events to AVL Operation modes (Main / Sub / Criterion)."""
from . import avl_map
from . import edo_loader


def sdv_for(ev):
    """Legacy alias: returns (display_name, group) for tabs."""
    main, sub = avl_map.avl_for(ev)
    _, _, sdv, _ = avl_map.scorecard(ev, {})
    label = f"{main} / {sub}" if main != "Unknown" else ev.get("label", ev["type"])
    return label, main


def scorecard(ev, m, issues=None):
    main, sub, sdv, rows = avl_map.scorecard(ev, m)
    return f"{main} / {sub}", main, rows


def catalog():
    return avl_map.catalog()


def criteria_source():
    return edo_loader.active_source()
