import json
import sys
from typing import List, Tuple, Dict, Optional, Any
import os, re
import csv
import pickle
import requests

from pyverilog.vparser.parser import parse
from pyverilog.vparser import ast as vast
from vcdvcd import VCDVCD

ollama_url = "http://98.225.176.62:11434/api/chat"
model_name = "gemma3:12b"  # As specified


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


def _get_llm_score(
    hdl_signal: Tuple[str, Optional[int]],
    vcd_candidate: Dict[str, Any],
    v_codes: str,  # New parameter: the full verilog source
    session: requests.Session,
    ollama_url: str,
    model_name: str,
    include_scopes: str,
    system_prompt: str,
) -> float:
    """
    Asks the LLM to provide a confidence score for a single HDL-VCD pair,
    providing the full Verilog source code as context in the system prompt.
    """
    hdl_key, hdl_width = hdl_signal
    vcd_full_path = vcd_candidate['full_path']
    vcd_width = vcd_candidate['width']

    # UPDATED: The system prompt now contains the Verilog source and the reasoning guide.

    # The user prompt is now very direct and focused.
    user_prompt = (
        f"Analyze the following pair based on the Verilog source and reasoning guide in your system prompt:\n\n"
        f"# Preferred Scopes (include_scopes): {include_scopes}\n\n"
        f"1. **Verilog Signal:**\n"
        f"   - Name: `{hdl_key}`\n"
        f"   - Width: {hdl_width}\n\n"
        f"2. **VCD Candidate:**\n"
        f"   - Path: `{vcd_full_path}`\n"
        f"   - Width: {vcd_width}\n\n"
        f"Provide a confidence score from 1 (poor match) to 10 (perfect match). "
        f"Your response MUST be a valid JSON object with a single key 'score' and a numeric value."
    )

    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "format": "json", "stream": False
    }

    try:
        response = session.post(ollama_url, json=payload, timeout=90)
        response.raise_for_status()
        api_response_data = response.json()
        llm_content_str = api_response_data.get("message", {}).get("content", "")
        llm_json_data = json.loads(llm_content_str)
        score = float(llm_json_data.get("score", 0.0))
        return score
    except Exception as e:
        print(f"Warning: LLM scoring failed for pair ({hdl_key}, {vcd_full_path}). Error: {e}. Assigning score 0.")
        return 0.0

def _prepare_data(
        verilog_files: List[str],
        vcd_path: str,
        design_name: str
) -> Tuple[Optional[List[Tuple[str, Optional[int]]]], Optional[Dict[str, List[Dict]]]]:
    """
    Loads and pre-processes all necessary data from Verilog and VCD files.

    This function handles:
    1. Parsing Verilog to get HDL signals.
    2. Caching the VCD parsing results to avoid reprocessing large files.
    3. Pre-processing the VCD data into an efficient lookup map.

    Args:
        verilog_files: List of paths to Verilog source files.
        vcd_path: Path to the VCD trace file.
        design_name: A unique name for the design, used for caching.

    Returns:
        A tuple containing (hdl_kws, vcd_candidates_map), or (None, None) on failure.
    """
    # 1. Get HDL keys + widths from Verilog files
    try:
        hdl_kws: List[Tuple[str, Optional[int]]] = _hdl_name_widths(verilog_files)
        print(f"Successfully parsed {len(hdl_kws)} signals from Verilog files.")
    except Exception as e:
        print(f"FATAL: Error parsing Verilog files. Aborting. Error: {e}")
        return None, None

    # 2. Load or parse VCD signals, using a cache
    output_dir = '../out'
    signals_cache_path = os.path.join(output_dir, f'{design_name}_vcd_signals.pkl')
    widths_cache_path = os.path.join(output_dir, f'{design_name}_vcd_widths.pkl')

    vcd_signals, vcd_widths = None, None
    try:
        if os.path.exists(signals_cache_path) and os.path.exists(widths_cache_path):
            print(f"Loading VCD index from cache: {signals_cache_path}")
            with open(signals_cache_path, 'rb') as f:
                vcd_signals = pickle.load(f)
            with open(widths_cache_path, 'rb') as f:
                vcd_widths = pickle.load(f)
    except Exception as e:
        print(f"Warning: Could not load VCD data from cache, will re-parse. Error: {e}")
        vcd_signals, vcd_widths = None, None

    if vcd_signals is None or vcd_widths is None:
        print(f"Parsing VCD file (cache not found or failed to load): {vcd_path}")
        try:
            _, vcd_signals, vcd_widths = _load_vcd_index(vcd_path)

            os.makedirs(output_dir, exist_ok=True)
            print(f"Saving VCD index to cache for future runs...")
            with open(signals_cache_path, 'wb') as f:
                pickle.dump(vcd_signals, f)
            with open(widths_cache_path, 'wb') as f:
                pickle.dump(vcd_widths, f)
            print("Cache saved successfully.")
        except Exception as e:
            print(f"FATAL: Error loading VCD file {vcd_path}. Aborting. Error: {e}")
            return None, None

    print(f"Loaded {len(vcd_signals)} signals from VCD index.")

    # 3. Pre-process VCD signals into an efficient lookup map
    vcd_candidates_map: Dict[str, List[Dict]] = {}
    for signal_path in vcd_signals:
        path_parts, var_name = _get_vcd_parts(signal_path)
        norm_var = _normalize_variable_name(var_name)
        candidate_info = {
            "full_path": signal_path,
            "original_var": var_name,
            "norm_path_parts": [_normalize_module_path_part(p) for p in path_parts],
            "width": vcd_widths.get(signal_path)
        }
        if norm_var not in vcd_candidates_map:
            vcd_candidates_map[norm_var] = []
        vcd_candidates_map[norm_var].append(candidate_info)

    return hdl_kws, vcd_candidates_map

def extract_signals_with_pyverilog(
        verilog_files: List[str],
        vcd_path: str,
        design_name: str,
        include_scopes: Optional[str] = None,
        exclude_scopes: Optional[str] = None,
) -> List[Tuple[str, Optional[int], Optional[str]]]:
    """
    Uses a hybrid Python-filter, LLM-score approach with a persistent HTTP session
    to find the best unique assignments.
    """

    hdl_kws, vcd_candidates_map = _prepare_data(verilog_files, vcd_path, design_name)
    if hdl_kws is None: return []

    tuple_file_path = f"../data/{design_name}/{design_name}_tuple.txt"

    triples: List[Tuple[str, Optional[int], Optional[str]]] = []

    if not os.path.exists(tuple_file_path):
        input(f"For {design_name}, vcd data preparation is done. Please make the tuple file.")
        print(f"Error: Mapping file not found at '{tuple_file_path}'.")
        # Return the original HDL keys with no matches
        return [(key, width, None) for key, width in hdl_kws]

    print(f"Reading final mappings from {tuple_file_path}...")
    try:
        with open(tuple_file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)

            # Skip the header row
            next(reader, None)

            for row in reader:
                if not row or len(row) < 3:
                    continue  # Skip empty or malformed rows

                # Unpack the row from the CSV
                hdl_key, width_str, vcd_path = row

                # Convert width from string to int or None
                width = int(width_str) if width_str and width_str.isdigit() else None

                # Convert an empty vcd_path string to None
                vcd_match = vcd_path if vcd_path else None

                triples.append((hdl_key, width, vcd_match))

    except Exception as e:
        print(f"Error reading or parsing the tuple file: {e}")
        return []

    print("Successfully loaded final mappings.")
    return triples
