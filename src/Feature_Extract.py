import sys
import csv
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
    graph, roots, nodes, node_attrs, indegree, outdegree, key_nodes, edges = Dot_Preprocess.read_dot_file(dot_file, sys.argv[2])
    vcd = VCDVCD(vcd_file, store_tvs=True)
    signal_keys = V_Preprocessing.extract_signals_with_pyverilog([v_file], vcd_file,
                                                                    include_scopes=["ibex_compressed_decoder_"],
                                                                    exclude_scopes=["bench", "tb", "test"],)

    for k, w, full in signal_keys:
        print(f"{k:<24} width={w:<4}  ->  {full}")

    for root in roots:
        # print(f"Root: {root}")
        paths = Dot_Preprocess.find_paths(graph, root)
        # print("Paths number:" + str(len(paths)))
        # for p in paths:
        #     annotated = [f"{node}" for node in p]
        #     print(" -> ".join(annotated))

    Features = Dot_Preprocess.extract_dot_features(graph, nodes, indegree, outdegree, node_attrs, key_nodes)
    Vcd_Preprocessing.extract_vcd_features(Features, node_attrs, vcd, signal_keys)

    def dump_features_to_csv(Feature, out_csv="../out/features.csv"):
        """
        Write Feature dict to CSV.
        Feature: dict[node] -> dict of features
        """
        fieldnames = set()
        for feat in Feature.values():
            fieldnames.update(feat.keys())
        fieldnames = ["node"] + sorted(fieldnames)

        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for node, feats in Feature.items():
                row = {"node": node}
                row.update(feats)
                writer.writerow(row)

        print(f"[INFO] Features written to {out_csv}")

    dump_features_to_csv(Features)

    with open("../out/edges.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "target"])
        writer.writeheader()
        for src, dst in edges:
            writer.writerow({"source": Features[src]["node_number"], "target": Features[dst]["node_number"]})
        print("[INFO] Edges written to edges.csv")