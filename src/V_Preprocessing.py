from typing import List, Tuple, Dict, Optional
import os, re

from pyverilog.vparser.parser import parse
from pyverilog.vparser import ast as vast
from vcdvcd import VCDVCD


class ManualASTVisitor:
    """
    A manual AST visitor that tracks module scope to produce 'module.variable' names.
    """

    def __init__(self):
        self.signals: Dict[str, Optional[int]] = {}
        self.current_module: Optional[str] = None  # State to track the current module

    def visit(self, node):
        """
        Recursively visits AST nodes to find signal declarations.
        """
        if node is None:
            return

        # --- Dispatcher: Act on specific node types ---
        node_type = type(node)

        # **MODIFICATION**: When a ModuleDef node is found, update the current scope.
        if node_type is vast.ModuleDef:
            self.current_module = node.name

        # Handle declaration nodes (Input, Output, Reg, etc.)
        if node_type in (vast.Input, vast.Output, vast.Inout, vast.Reg, vast.Wire, vast.Variable, vast.Parameter):
            self._handle_declaration(node)

        # --- Traversal: Recursively visit all children ---
        for child in node.children():
            self.visit(child)

    def _handle_declaration(self, node):
        """Extracts name and width from a declaration node."""
        if not hasattr(node, 'name') or not node.name:
            return

        # **MODIFICATION**: Prepend the module name if we are in a module's scope.
        if self.current_module:
            full_name = f"{self.current_module}.{node.name}"
        else:
            full_name = node.name  # Fallback for variables declared outside a module

        width_node = getattr(node, 'width', None)
        width = self._calculate_width(width_node)

        # Use the new full name as the dictionary key
        self.signals[full_name] = width

    def _calculate_width(self, width_node: Optional[vast.Width]) -> Optional[int]:
        """Calculates the bit width from a Width AST node."""
        if width_node:
            try:
                msb_str = width_node.msb.value
                lsb_str = width_node.lsb.value
                msb = int(msb_str)
                lsb = int(lsb_str)
                return abs(msb - lsb) + 1
            except (AttributeError, ValueError, TypeError):
                return None
        return 1

# ---------- Build HDL name->width from Verilog (PyVerilog) ----------
def _hdl_name_widths(verilog_files: List[str]) -> List[Tuple[str, Optional[int]]]:
    try:
        ast, _ = parse(verilog_files, debug=False)
        visitor = ManualASTVisitor()
        visitor.visit(ast)
        results = sorted(list(visitor.signals.items()))
        return results
    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        return []

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

# --- HELPER FUNCTIONS FOR MATCHING ---
def _normalize_module_path_part(name: str) -> str:
    """
    Normalizes a name for comparison by lowercasing, removing underscores,
    and stripping trailing digits.
    e.g., "Inv_MixColumn0" -> "invmixcolumn"
    """
    # Remove trailing digits
    name = re.sub(r'\d+$', '', name)
    # Lowercase and remove underscores
    return name.lower().replace('_', '')

def _normalize_variable_name(name: str) -> str:
    """
    Normalizes a variable name for comparison.
    Lowercases and removes underscores, but DOES NOT strip digits.
    e.g., "a33" -> "a33"
    """
    return name.lower().replace('_', '')

def _get_vcd_parts(vcd_signal: str) -> Tuple[List[str], str]:
    """
    Splits a VCD signal into its hierarchy path and base variable name.
    e.g., "top.dut.mod.var[7:0]" -> (['top', 'dut', 'mod'], 'var')
    """
    parts = vcd_signal.split('.')
    base_var = re.sub(r'\[[^\]]+\]$', '', parts[-1]).strip()
    return parts[:-1], base_var

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
    """
    include_scopes = include_scopes or []
    exclude_scopes = exclude_scopes or []

    # 1) HDL keys + widths
    hdl_kws: List[Tuple[str, Optional[int]]] = _hdl_name_widths(verilog_files)

    # 2) VCD index
    _, vcd_signals, vcd_widths = _load_vcd_index(vcd_path)
    # print("VCD signals:")
    for full in vcd_signals:
        # print(f"{full}")

        # Pre-process VCD signals for efficient lookup
        vcd_candidates_map: Dict[str, List[Dict]] = {}
        for signal_path in vcd_signals:
            path_parts, var_name = _get_vcd_parts(signal_path)
            # Use the correct normalization for the variable name (no digit stripping)
            norm_var = _normalize_variable_name(var_name)

            candidate_info = {
                "full_path": signal_path,
                # Use module-specific normalization for the path parts
                "norm_path_parts": [_normalize_module_path_part(p) for p in path_parts],
                "width": vcd_widths.get(signal_path)
            }

            if norm_var not in vcd_candidates_map:
                vcd_candidates_map[norm_var] = []
            vcd_candidates_map[norm_var].append(candidate_info)

        # Iterate through HDL signals and find the best VCD match
        triples: List[Tuple[str, Optional[int], Optional[str]]] = []
        for hdl_key, hdl_width in hdl_kws:

            try:
                hdl_module_name, hdl_var_name = hdl_key.split('.', 1)
                # Use the correct normalization for each part
                norm_hdl_module = _normalize_module_path_part(hdl_module_name)
                norm_hdl_var = _normalize_variable_name(hdl_var_name)
            except ValueError:
                norm_hdl_module = ""
                norm_hdl_var = _normalize_variable_name(hdl_key)

            best_match_path: Optional[str] = None
            highest_score = -float('inf')

            # This lookup now works correctly because norm_hdl_var is distinct (e.g., 'a00', 'a33')
            candidates = vcd_candidates_map.get(norm_hdl_var, [])

            for cand in candidates:
                score = 0

                if norm_hdl_module and norm_hdl_module in cand["norm_path_parts"]:
                    score += 10

                if hdl_width is not None and hdl_width == cand["width"]:
                    score += 5

                for scope in include_scopes:
                    if scope in cand["full_path"]:
                        score += 2
                for scope in exclude_scopes:
                    if scope in cand["full_path"]:
                        score -= 4

                score -= len(cand["norm_path_parts"]) * 0.1

                if score > highest_score:
                    highest_score = score
                    best_match_path = cand["full_path"]

            triples.append((hdl_key, hdl_width, best_match_path))

        return triples