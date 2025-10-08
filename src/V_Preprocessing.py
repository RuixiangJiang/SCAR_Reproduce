import json
from typing import List, Tuple, Dict, Optional, Any
import os, re
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

def _get_name_parts(name: str) -> List[str]:
    """
    Splits a CamelCase or snake_case name into a list of lowercase words.
    e.g., "RSA_SequencerBlock" -> ['rsa', 'sequencer', 'block']
    """
    # Add a space before capital letters (for CamelCase)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    # Replace underscores with spaces
    s = s.replace('_', ' ')
    return s.lower().split()


def _get_name_similarity(hdl_name: str, vcd_name: str) -> float:
    """
    Calculates a similarity score (0.0 to 1.0) between two module/instance names.
    """
    if not hdl_name or not vcd_name:
        return 0.0

    # Perfect match is best
    if hdl_name == vcd_name:
        return 1.0

    # Word-based prefix matching (most powerful)
    hdl_words = _get_name_parts(hdl_name)
    vcd_words = _get_name_parts(vcd_name)

    if not hdl_words or not vcd_words:
        return 0.0

    matches = 0
    for v_word in vcd_words:
        if any(h_word.startswith(v_word) for h_word in hdl_words):
            matches += 1

    word_match_quality = matches / len(vcd_words)
    if word_match_quality == 1.0:
        return 0.9  # Return a very high score for a perfect word-prefix match

    # Fallback to simple startswith on normalized names
    norm_hdl = hdl_name.lower().replace('_', '')
    norm_vcd = vcd_name.lower().replace('_', '')
    if norm_hdl.startswith(norm_vcd) or norm_vcd.startswith(norm_hdl):
        return 0.7

    return 0.0

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

def _is_subsequence(short_str: str, long_str: str) -> bool:
    """Checks if short_str is an ordered subsequence of long_str."""
    it = iter(long_str)
    return all(c in it for c in short_str)


def _calculate_match_score(
        cand: Dict[str, Any],
        hdl_signal: Tuple[str, Optional[int]],
        include_scopes: List[str],
        exclude_scopes: List[str]
) -> float:
    """
    Calculates the matching score, correctly handling partial word-based matches.
    """
    hdl_key, hdl_width = hdl_signal

    try:
        hdl_module_name, hdl_var_name = hdl_key.split('.', 1)
    except ValueError:
        hdl_module_name, hdl_var_name = "", hdl_key

    score = 0.0

    path_score = 0.0
    if hdl_module_name and cand["norm_path_parts"]:

        hdl_words = _get_name_parts(hdl_module_name)
        vcd_instance_name = cand["full_path"].split('.')[-2]
        vcd_instance_words = _get_name_parts(vcd_instance_name)

        match_quality = 0.0
        if vcd_instance_words and hdl_words:
            matches = 0
            for v_word in vcd_instance_words:
                if any(h_word.startswith(v_word) for h_word in hdl_words):
                    matches += 1
            match_quality = matches / len(vcd_instance_words)

        # --- CORRECTED LOGIC ---
        # If there's a significant match (at least 50%), award a proportional large bonus.
        if match_quality >= 0.5:
            path_score = match_quality * 20.0
        else:
            # Fallback to ancestor check only if instance match is poor.
            norm_hdl_module = _normalize_module_path_part(hdl_module_name)
            best_ancestor_ratio = 0.0
            for vcd_part in cand["norm_path_parts"][:-1]:
                if vcd_part in norm_hdl_module:
                    ratio = len(vcd_part) / len(norm_hdl_module)
                    if ratio > best_ancestor_ratio: best_ancestor_ratio = ratio

            if best_ancestor_ratio > 0.2:
                path_score = best_ancestor_ratio * 5
            else:
                path_score = -5

    score += path_score

    if hdl_width is not None and hdl_width == cand["width"]: score += 5
    if hdl_var_name != cand["original_var"]: score -= 3
    for scope in include_scopes:
        if scope in cand["full_path"]: score += 2
    for scope in exclude_scopes:
        if scope in cand["full_path"]: score -= 4
    score -= len(cand["norm_path_parts"]) * 0.1

    return score

def _get_llm_match(
    hdl_signal: Tuple[str, Optional[int]],
    vcd_candidates: List[str],
    ollama_url=ollama_url,
    model_name=model_name
) -> Optional[str]:
    """
    Uses an Ollama LLM to choose the best VCD match from a list of candidates.
    """
    if not vcd_candidates:
        return None

    hdl_key, hdl_width = hdl_signal

    system_prompt = (
        "You are an expert hardware verification engineer. Your task is to find the single best "
        "match for a Verilog signal from a list of VCD (Value Change Dump) signal candidates "
        "generated during a simulation. Analyze the module hierarchy, instance names, signal names, "
        "and common abbreviations (e.g., 'SEQ_BLK' for 'SequencerBlock', 'reg' for 'register')."
    )

    # Format the candidate list for the prompt
    candidate_list_str = "\n".join(f"- {c}" for c in vcd_candidates)

    user_prompt = (
        f"I have the following signal from a Verilog source file:\n"
        f"Name: {hdl_key}\n"
        f"Width: {hdl_width}\n\n"
        f"Here is a list of plausible VCD candidates:\n"
        f"{candidate_list_str}\n\n"
        f"Based on your analysis, which single VCD candidate is the best and most logical match? "
        f"Your response MUST be a valid JSON object with a single key, 'best_match', "
        f"whose value is the full string of your chosen VCD signal from the list, or null if no "
        f"candidate is a good match."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "format": "json",  # Crucial for getting a parsable response
        "stream": False
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=90) # 90 second timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # The response from Ollama with format='json' is a JSON object where the
        # 'content' field is a *string* that itself contains JSON.
        api_response_data = response.json()
        llm_content_str = api_response_data.get("message", {}).get("content", "")

        if not llm_content_str:
            print(f"Warning: LLM returned empty content for {hdl_key}")
            return None

        # Parse the JSON string from the content
        llm_json_data = json.loads(llm_content_str)
        best_match = llm_json_data.get("best_match")

        # Final check to ensure the LLM didn't hallucinate a new signal name
        if best_match and best_match in vcd_candidates:
            return best_match
        else:
            if best_match:
                print(f"Warning: LLM returned a signal '{best_match}' not in the candidate list for {hdl_key}.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"\n--- ERROR ---")
        print(f"Could not connect to the Ollama API at {ollama_url}.")
        print(f"Please ensure the Ollama server is running and accessible.")
        print(f"Error details: {e}")
        return None # Return None on network error
    except (json.JSONDecodeError, KeyError) as e:
        print(f"\n--- ERROR ---")
        print(f"Could not parse the JSON response from the LLM for {hdl_key}.")
        print(f"Error details: {e}")
        return None

# ---------- Public: extract (hdl_key, width, vcd_full_name) ----------
def extract_signals_with_pyverilog(
        verilog_files: List[str],
        vcd_path: str,
        include_scopes: Optional[List[str]] = None,
        exclude_scopes: Optional[List[str]] = None,
) -> List[Tuple[str, Optional[int], Optional[str]]]:
    """
    Parses HDL signals and uses a local LLM via the Ollama API to map them
    to the best-matching unique VCD signal.
    """
    # 1) Get HDL keys + widths (this function remains the same)
    hdl_kws: List[Tuple[str, Optional[int]]] = _hdl_name_widths(verilog_files)

    # 2) Get and pre-process VCD signals (this logic remains the same)
    try:
        _, vcd_signals, vcd_widths = _load_vcd_index(vcd_path)
    except Exception as e:
        print(f"Error loading VCD file {vcd_path}: {e}")
        return [(key, width, None) for key, width in hdl_kws]

    vcd_candidates_map: Dict[str, List[Dict]] = {}
    for signal_path in vcd_signals:
        _, var_name = _get_vcd_parts(signal_path)
        norm_var = _normalize_variable_name(var_name)
        if norm_var not in vcd_candidates_map:
            vcd_candidates_map[norm_var] = []
        vcd_candidates_map[norm_var].append({"full_path": signal_path})

    # 3) Iterate through HDL signals and use the LLM to find the best match
    triples: List[Tuple[str, Optional[int], Optional[str]]] = []
    print(f"Starting LLM matching process for {len(hdl_kws)} HDL signals...")
    for i, (hdl_key, hdl_width) in enumerate(hdl_kws):
        norm_hdl_var = _normalize_variable_name(hdl_key.split('.')[-1])

        # Create a focused shortlist of candidates to send to the LLM
        candidates = vcd_candidates_map.get(norm_hdl_var, [])
        candidate_paths = [c['full_path'] for c in candidates]

        print(f"({i + 1}/{len(hdl_kws)}) Resolving '{hdl_key}' among {len(candidate_paths)} candidates...")

        best_match = _get_llm_match(
            (hdl_key, hdl_width),
            candidate_paths,
            ollama_url,
            model_name
        )

        triples.append((hdl_key, hdl_width, best_match))

    # Note: This approach doesn't guarantee uniqueness. An LLM might pick the same
    # VCD signal for two different HDL signals. A second "assignment" pass would be
    # needed for a strictly unique mapping, similar to our previous rule-based solution.

    return triples


if __name__ == "__main__":
    hdl_signal = ('RSA_Register32.non_existent_var', 8)

    vcd_candidates = [
        'top.RSA_tb.RSA.MULT_BLK.REG_X.d[31:0]',
        'top.RSA_tb.RSA.MULT_BLK.REG_X.q[31:0]'
    ]

    print(_get_llm_match(hdl_signal, vcd_candidates))