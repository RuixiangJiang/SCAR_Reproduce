import re
from collections import defaultdict
import os
import pydot
from vcdvcd import VCDVCD


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

_SIG_SLICE_RE = re.compile(r"\b([A-Za-z_]\w*)\s*(?:\[\s*(\d+)(?::\s*(\d+))?\s*\])?")
_LITERAL_RE = re.compile(r"\b\d+'\s*[bBoOdDhH]\s*[0-9a-fA-FxXzZ_]+\b")
_REPL_COUNT_RE = re.compile(r"\{\s*\d+\s*\{")
_BLACKLIST = {
    "assign","case","endcase","if","else","begin","end","always",
    "wire","reg","logic","OPCODE_JAL"
}
def parse_label_slices(label: str):
    """
    Parse registers in the label.
    """
    if not label:
        return []

    lines = label.splitlines()
    if lines and re.match(r"^\s*\d+:[A-Za-z_]\w*\s*$", lines[0]):
        label_body = "\n".join(lines[1:])
    else:
        label_body = label

    s = _LITERAL_RE.sub(" ", label_body)
    s = _REPL_COUNT_RE.sub("{ {", s)
    s = s.replace("{", " ").replace("}", " ")
    s = s.replace("~", " ")
    s = s.replace(",", " ")
    # print(f"s = {s}")

    results = []
    for m in _SIG_SLICE_RE.finditer(s):
        base = m.group(1)
        if not base or base.lower() in _BLACKLIST:
            continue

        hi = m.group(2)
        lo = m.group(3)
        # print(f"{base}:{hi}:{lo}")

        if hi is not None and lo is None:
            hi_i = int(hi)
            lo_i = int(hi)
            results.append((base, hi_i, lo_i))
        elif hi is not None and lo is not None:
            results.append((base, int(hi), int(lo)))
        else:
            results.append((base, None, None))

    return results

def resolve_signal_key(signal_keys, base):
    """
    map the register name in label to signal key in VCDVCD.
    """
    for hdl_key, _, vcd_full in signal_keys:
        if hdl_key == base:
            return vcd_full
    return None

def extract_vcd_features(Feature, node_attrs, vcd, signal_keys):
    per_bit_toggles = {}
    widths = {}

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
        print(f"HD Total for {sig_key}: {toggles}")

    for node in Feature.keys():
        label = node_attrs.get(node, {}).get("label", "") or ""
        specs = parse_label_slices(label)

        # print(f"label: {label}\nspecs: {specs}")

        total = 0
        components = []

        for base, hi, lo in specs:
            sig_key = resolve_signal_key(signal_keys, base)
            # print(f"sig_key: {sig_key}")
            if sig_key is None:
                continue

            width = widths.get(sig_key, 1)
            toggles = per_bit_toggles[sig_key]  # MSB..LSB
            # print(f"width: {width}, toggles: {toggles}")

            if hi is None:
                hi = width - 1
            if lo is None:
                lo = 0

            hi_, lo_ = (hi, lo) if hi >= lo else (lo, hi)
            hi_ = min(hi_, width - 1)
            lo_ = max(lo_, 0)
            if lo_ > hi_:
                continue

            # print(f"base: {base}, hi_: {hi_}, lo_: {lo_}")

            for bit in range(lo_, hi_ + 1):
                idx = width - 1 - bit
                if 0 <= idx < len(toggles):
                    total += toggles[idx]
                    components.append((f"{base}[{hi}:{lo}]", bit, toggles[idx]))

        Feature[node]["Hamming distance"] = total

    # print(f"vcd.signals: {vcd.signals}")

    return per_bit_toggles, widths