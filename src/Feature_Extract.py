import sys
from vcdvcd import VCDVCD

import Dot_Preprocess
import Vcd_Preprocessing
import V_Preprocessing


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("python tree_paths.py <dep_file> <key_register_name>")
        sys.exit(1)

    dot_file = "../data/" + sys.argv[1] + ".dot"
    vcd_file = "../data/" + sys.argv[1] + ".vcd"
    v_file = "../data/" + sys.argv[1] + ".v"
    graph, roots, nodes, node_attrs, indegree, outdegree = Dot_Preprocess.read_dot_file(dot_file)
    vcd = VCDVCD(vcd_file, store_tvs=True)
    signal_keys = V_Preprocessing.extract_signals_with_pyverilog([v_file], vcd_file,
                                                                    include_scopes=["ibex_compressed_decoder_"],
                                                                    exclude_scopes=["bench", "tb", "test"],)

    for k, w, full in signal_keys:
        print(f"{k:<24} width={w:<4}  ->  {full}")

    if not roots:
        print("Root node not found！")
        sys.exit(1)

    for root in roots:
        # print(f"Root: {root}")
        paths = Dot_Preprocess.find_paths(graph, root)
        # print("Paths number:" + str(len(paths)))
        # for p in paths:
        #     annotated = [f"{node}" for node in p]
        #     print(" -> ".join(annotated))

    Features = Dot_Preprocess.extract_dot_features(nodes, indegree, outdegree, node_attrs)
    Vcd_Preprocessing.extract_vcd_features(Features, node_attrs, vcd, signal_keys)

    for node in nodes:
        print(f"{node} features: {Features[node]}")