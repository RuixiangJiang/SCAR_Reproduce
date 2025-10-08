import ast
import re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import os
import pydot
import csv
import requests
import json
import re
from vcdvcd import VCDVCD

from V_Preprocessing import _normalize_module_path_part, _normalize_variable_name, _get_vcd_parts


def norm_bits(val: str, width: int):
    """
    Transform VCD value to formal binary string.
    E.g. the original string is 0 (8 bit), we should get 00000000; for b10101010, we should get 10101010.
    """
    s = str(val)
    if s.startswith(("b", "B")):
        s = s[1:]
    elif s in ("0", "1"):
        s = s * width
    if not set(s) <= {"0", "1"}:
        return None
    if width and len(s) < width:
        s = s.zfill(width)
    return s

def bit_toggles_per_signal(tv, width):
    """
    Calculate how many times each bit has been toggled.
    """
    prev = None
    toggles = [0] * width
    for t, v in tv:
        bs = norm_bits(v, width)
        if bs is None:
            prev = None
            continue
        if prev is not None:
            m = max(len(prev), len(bs))
            a = prev.zfill(m)
            b = bs.zfill(m)
            a = a[-width:]
            b = b[-width:]
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    toggles[i] += 1
        prev = bs
    return toggles


def _parse_node_string_for_llm(node_str: str) -> tuple[str, str]:
    """Parses the Node string into (module_path, code) for the prompt."""
    if '\n' not in node_str:
        return "", node_str

    first_line, code = node_str.split('\n', 1)

    match = re.match(r'^(.+?)\.\d+:', first_line)
    if match:
        return match.group(1), code

    return "", code


def _extract_variables_from_code_for_llm(code: str) -> list[str]:
    """Extracts potential variable names from a line of Verilog code."""
    keywords = {'module', 'endmodule', 'input', 'output', 'reg', 'wire', 'assign', 'always', 'if', 'else', 'case',
                'endcase'}
    variables = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', code)
    return sorted(list(set([v for v in variables if v not in keywords])))


def get_mapping_for_node_with_llm(node_line: str, all_vcd_signals_str: str) -> Tuple[
    str, List[Tuple[str, Optional[str], int, int]]]:
    """
    Invokes a local LLM to map all variables in a single Node line to their
    corresponding VCD signals and determine the bit ranges.

    Args:
        node_line: A single string from the 'Node' column (e.g., "SEQ_BLK.START_MR.439:AS\nStart = ~rgt & Pc;").
        all_vcd_signals_str: A single string containing all VCD signals, separated by newlines.

    Returns:
        A tuple in the format: (Node_Line, [(variable, vcd_signal, hi, lo), ...])
    """
    ollama_url = "http://98.225.176.62:11434/api/chat"
    model_name = "gemma3:12b"

    # --- 1. Construct the Prompt ---
    system_prompt = (
        "You are an expert hardware verification engineer specializing in data correlation. Your task is to analyze a line of Verilog code from a control-flow graph and map every variable in it to its corresponding hierarchical signal from a VCD trace file. You must also determine the exact bit range being accessed.\n\n"
        "**Reasoning Guide:**\n"
        "1.  **Context is Key:** The `Node` string contains a module path (e.g., `SEQ_BLK.START_MR`). This is your primary clue. A variable from the code MUST belong to an instance matching this path in the VCD.\n"
        "2.  **Abbreviations:** VCD instance names (`SEQ_BLK`) are often abbreviations of Verilog module names (`SequencerBlock`).\n"
        "3.  **Bit Ranges:** If the code uses `pc[10]`, `hi` and `lo` are both `10`. If it uses `pc[10:0]`, `hi` is `10` and `lo` is `0`. For a whole variable access like `Start`, `hi` and `lo` correspond to its full width (e.g., `0` and `0` for a 1-bit signal).\n\n"
        "**Common Mistakes to Avoid:**\n"
        "- **DO NOT** identify parts of the Node's name (e.g., `SEQ_BLK`, `START_MR`, `439`, `AS`, `IF`) as variables. Only identify variables from the actual Verilog code snippet.\n"
        "- **DO NOT** treat constant values (e.g., `32'h00000000`, `1'b0`) as variables.\n"
        "- The `vcd_signal` you choose **MUST** be an exact string from the provided candidate list. Do not invent or modify a VCD path. If no candidate is a good match, the value for `vcd_signal` must be `null`."
    )

    user_prompt = (
        f"# VCD Signal Candidates\n"
        f"This is the complete list of available signals from the VCD trace:\n"
        f"```\n{all_vcd_signals_str}\n```\n\n"
        f"# Task: Analyze and Map the following Node\n\n"
        f"**Node:**\n"
        f"```\n{node_line}\n```\n\n"
        f"For the Verilog code in the `Node` above, perform the following steps for every valid variable you find:\n"
        f"1.  Identify the variable name and any bit-slicing used (e.g., `[10]`, `[63:32]`).\n"
        f"2.  Using the module context from the `Node` and the reasoning guide in your system prompt, find the single best hierarchical match from the VCD signal list.\n"
        f"3.  Determine the `hi` and `lo` bit indices for the access.\n"
        f"4.  Adhere strictly to the 'Common Mistakes to Avoid' list.\n\n"
        f"# OUTPUT FORMAT\n"
        f"Your response MUST be a single valid JSON object with one key, 'mappings'. The value must be a list of objects. Each object must have four keys: 'variable' (the name from the code), 'vcd_signal' (the best match from the list, or null), 'hi' (an integer), and 'lo' (an integer)."
    )

    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "format": "json",
        "stream": False
    }

    # --- 2. Call the API and Parse the Response ---
    try:
        response = requests.post(ollama_url, json=payload, timeout=120)  # Generous 2-minute timeout
        response.raise_for_status()

        api_response_data = response.json()
        llm_content_str = api_response_data.get("message", {}).get("content", "")

        if not llm_content_str:
            print(f"Warning: LLM returned empty content for node: {node_line}")
            return (node_line, [])

        # Parse the JSON response and format it into the final tuple
        llm_json_data = json.loads(llm_content_str)
        mappings = llm_json_data.get("mappings", [])

        # Convert list of dicts to list of tuples
        result_tuples = [
            (m.get('variable'), m.get('vcd_signal'), m.get('hi', 0), m.get('lo', 0))
            for m in mappings
        ]

        return (node_line, result_tuples)

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama API for node '{node_line}'. Error: {e}")
        return (node_line, [])
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing LLM JSON response for node '{node_line}'. Error: {e}")
        return (node_line, [])

def extract_vcd_features(Feature, node_attrs, vcd, design_name, sig_key_str):
    per_bit_toggles = {}
    widths = {}
    toggle_cache_path = os.path.join(f"../data/{design_name}/{design_name}_toggle.txt")
    if os.path.exists(toggle_cache_path):
        print(f"Loading toggle counts from cache: {toggle_cache_path}")
        with open(toggle_cache_path, 'r', newline='') as f_cache:
            reader = csv.reader(f_cache)
            next(reader, None)
            for row in reader:
                sig_key, width_str, toggles_str = row
                width = int(width_str)
                toggles = [int(t) for t in toggles_str.split(' ')]
                widths[sig_key] = width
                per_bit_toggles[sig_key] = toggles
        print("Successfully loaded toggle counts from cache.")
    else:
        print("Calculating toggle counts (this may take a while)...")
        for sig_key in vcd.signals:
            sig = vcd[sig_key]
            width = getattr(sig, "size", None)
            if width is None:
                try:
                    ref = sig.references[0]
                    width = vcd.data[ref]["nets"][0].get("size", 1)
                except Exception:
                    width = 1
            width = int(width) if width else 1
            widths[sig_key] = width
            toggles = bit_toggles_per_signal(sig.tv, width)
            per_bit_toggles[sig_key] = toggles
            # print(f"HD Total for {sig_key}: {toggles}")
        print(f"Saving toggle counts to cache: {toggle_cache_path}")
        with open(toggle_cache_path, 'w', newline='') as f_cache:
            writer = csv.writer(f_cache)
            writer.writerow(['sig_key', 'width', 'toggles'])
            for sig_key, toggles_list in per_bit_toggles.items():
                width = widths[sig_key]
                toggles_str = ' '.join(map(str, toggles_list))
                writer.writerow([sig_key, width, toggles_str])
        print("Cache saved successfully.")

    node_match_path = os.path.join('../data', design_name, f'{design_name}_node_matches.csv')
    matches_dict = {}
    if not os.path.exists(node_match_path):
        raise FileNotFoundError(f"Mapping file not found. Please ensure it exists at: {os.path.abspath(node_match_path)}")
    else:
        with open(node_match_path, 'r', newline='') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                node_str, mappings_str = row
                try:
                    mappings_list = eval(mappings_str)
                except Exception as e:
                    print(f"Warning: Could not parse mappings for node: {node_str} with value: {mappings_str} because of {e}")
                    mappings_list = []
                matches_dict[node_str] = mappings_list

    for node in Feature.keys():
        label = node_attrs.get(node, {}).get("label", "") or ""
        print(f"Processing node: {label} with dict {matches_dict[label]}")
        total = 0
        for sig_key, hi, lo in matches_dict[label]:
            width = widths.get(sig_key, 1)
            toggles = per_bit_toggles[sig_key]
            print(f"    sigkey = {sig_key}, hi = {hi}, lo = {lo}, width: {width}, toggles: {toggles}")
            for bit in range(lo, hi + 1):
                idx = width - 1 - bit
                if 0 <= idx < len(toggles):
                    total += toggles[idx]

        Feature[node]["Hamming distance"] = total
    #
    # print(f"vcd.signals: {vcd.signals}")

    return per_bit_toggles, widths