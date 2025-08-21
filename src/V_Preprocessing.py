from typing import List, Tuple, Dict, Optional
import os, re

from pyverilog.vparser.parser import parse
from pyverilog.vparser import ast as vast
from vcdvcd import VCDVCD

# ---------- Utilities: evaluate ints & width ----------
def _eval_int(node) -> Optional[int]:
    if node is None:
        return None
    if isinstance(node, vast.IntConst):
        s = node.value
        try:
            return int(s, 0)
        except Exception:
            try:
                if "'" in s:
                    _, base_val = s.split("'", 1)
                    base_char = base_val[0].lower()
                    val = base_val[1:].replace("_", "")
                    base = {"d":10, "h":16, "b":2, "o":8}.get(base_char, 10)
                    return int(val, base)
            except Exception:
                return None
            return None
    if isinstance(node, vast.UnaryOperator):
        v = _eval_int(node.right)
        if v is None: return None
        if node.__class__.__name__ == 'Uminus': return -v
        return v
    if isinstance(node, vast.Plus):
        l = _eval_int(node.left); r = _eval_int(node.right)
        return None if l is None or r is None else l + r
    if isinstance(node, vast.Minus):
        l = _eval_int(node.left); r = _eval_int(node.right)
        return None if l is None or r is None else l - r
    if isinstance(node, vast.Times):
        l = _eval_int(node.left); r = _eval_int(node.right)
        return None if l is None or r is None else l * r
    if isinstance(node, vast.Divide):
        l = _eval_int(node.left); r = _eval_int(node.right)
        try:
            return None if l is None or r is None else l // r
        except Exception:
            return None
    return None

def _width_from_widthnode(widthnode) -> Optional[int]:
    if widthnode is None:
        return 1
    msb = _eval_int(widthnode.msb)
    lsb = _eval_int(widthnode.lsb)
    if msb is None or lsb is None:
        return None
    return abs(msb - lsb) + 1

# ---------- Build HDL name->width from Verilog (PyVerilog) ----------
def _hdl_name_widths(verilog_files: List[str]) -> List[Tuple[str, Optional[int]]]:
    files = [os.path.abspath(f) for f in verilog_files]
    ast, _ = parse(files)

    name2width: Dict[str, Optional[int]] = {}

    def record(name: str, widthnode):
        width = _width_from_widthnode(widthnode)
        if name not in name2width:
            name2width[name] = width
        else:
            old = name2width[name]
            if old is None and width is not None:
                name2width[name] = width
            elif old is not None and width is not None:
                name2width[name] = max(old, width)

    def visit(node):
        for c in node.children():
            # Port: Ioport -> Input/Output/Inout with optional width
            if isinstance(c, vast.Ioport):
                decl = c.first
                widthnode = getattr(decl, "width", None)
                second = c.second
                if isinstance(second, (list, tuple)):
                    for s in second:
                        n = getattr(s, "name", None)
                        if n: record(n, widthnode)
                else:
                    n = getattr(second, "name", None)
                    if n: record(n, widthnode)

            # Decl: Wire/Reg/Integer (PyVerilog is Verilog-2005; no 'Logic')
            if isinstance(c, vast.Decl):
                for item in c.list:
                    if isinstance(item, (vast.Wire, vast.Reg, vast.Integer)):
                        widthnode = getattr(item, "width", None)
                        if hasattr(item, "name") and item.name:
                            names = [item]
                        elif hasattr(item, "names"):
                            names = item.names
                        else:
                            names = [item]
                        for n in names:
                            nm = getattr(n, "name", None)
                            if nm: record(nm, widthnode)

            visit(c)

    visit(ast)
    return sorted(name2width.items(), key=lambda x: x[0])

# ---------- Build VCD index ----------
def _load_vcd_index(vcd_path: str):
    vcd = VCDVCD(vcd_path, store_tvs=True)
    widths: Dict[str, Optional[int]] = {}
    for full in vcd.signals:
        sig = vcd[full]
        w = getattr(sig, "size", None)
        if w is None:
            try:
                ref = sig.references[0]
                w = vcd.data[ref]["nets"][0].get("size", None)
            except Exception:
                w = None
        widths[full] = int(w) if w is not None else None
    return vcd, list(vcd.signals), widths

def _base_of(full: str) -> str:
    base = full.split(".")[-1]
    return re.sub(r"\[.*\]$", "", base)

def _score_candidate(
    key: str, width: Optional[int], full: str, full_width: Optional[int],
    include_scopes: List[str], exclude_scopes: List[str]
) -> int:
    s = 0
    if width is not None and full_width is not None and width == full_width:
        s += 5
    if full.endswith("." + key) or full == key:
        s += 3
    elif _base_of(full) == key:
        s += 1
    lname = full.lower()
    if any(inc.lower() in lname for inc in include_scopes):
        s += 4
    if any(exc.lower() in lname for exc in exclude_scopes):
        s -= 4
    s += full.count(".")
    return s

# ---------- Public: extract (hdl_key, width, vcd_full_name) ----------
def extract_signals_with_pyverilog(
    verilog_files: List[str],
    vcd_path: str,
    include_scopes: Optional[List[str]] = None,
    exclude_scopes: Optional[List[str]] = None,
) -> List[Tuple[str, Optional[int], Optional[str]]]:
    """
    Parse HDL (.v) to get (hdl_key, width), and map each key to the best-matching
    VCD hierarchical signal. Returns a list of triples:
        (hdl_key, width, vcd_full_name or None)

    Args:
        verilog_files: a path or a list of paths to Verilog files.
        vcd_path: path to the VCD file.
        include_scopes: prefer VCD signals whose hierarchical name contains any of these substrings (e.g., DUT name).
        exclude_scopes: penalize VCD signals whose hierarchical name contains any of these substrings (e.g., 'bench','tb').

    Notes:
        - Requires 'iverilog' available for PyVerilog preprocessing (or set env PYVERILOG_IVERILOG=/path/to/iverilog).
        - PyVerilog parses Verilog-2005; SystemVerilog 'logic' is not recognized.
    """
    include_scopes = include_scopes or []
    exclude_scopes = exclude_scopes or []

    # 1) HDL keys + widths
    hdl_kws: List[Tuple[str, Optional[int]]] = _hdl_name_widths(verilog_files)

    # 2) VCD index
    _, vcd_signals, vcd_widths = _load_vcd_index(vcd_path)

    # Pre-index VCD by base name
    by_base: Dict[str, List[str]] = {}
    for full in vcd_signals:
        b = _base_of(full)
        by_base.setdefault(b, []).append(full)

    # 3) Map each HDL key -> best VCD signal
    triples: List[Tuple[str, Optional[int], Optional[str]]] = []
    for key, width in hdl_kws:
        cands = by_base.get(key, [])
        if not cands:
            cands = [full for full in vcd_signals if full.endswith("." + key)]
        best_full, best_score = None, -10**9
        for full in cands:
            sc = _score_candidate(key, width, full, vcd_widths.get(full),
                                  include_scopes, exclude_scopes)
            if sc > best_score:
                best_score, best_full = sc, full
        triples.append((key, width, best_full))
    return triples
