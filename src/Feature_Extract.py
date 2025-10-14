import pickle
import sys
import csv
import glob
import os

from vcdvcd import VCDVCD

import Dot_Preprocess
import Vcd_Preprocessing
import V_Preprocessing
import Label_Preprocessing


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("python tree_paths.py <dep_file> <key_register_name>")
        sys.exit(1)

    dot_file = f"../data/{sys.argv[1]}/{sys.argv[1]}.dot"
    vcd_file = f"../data/{sys.argv[1]}/{sys.argv[1]}.vcd"
    vcd_pkl_file = f"../data/{sys.argv[1]}/{sys.argv[1]}_vcd.pkl"
    v_files = glob.glob(os.path.join("../data/" + sys.argv[1], "*.v"))
    graph, roots, nodes, node_attrs, indegree, outdegree, key_nodes, edges = Dot_Preprocess.read_dot_file(dot_file, sys.argv[2], sys.argv[1])
    # signal_keys = V_Preprocessing.extract_signals_with_pyverilog(v_files, vcd_file, sys.argv[1])

    # for k, w, full in signal_keys:
    #     print(f"{k:<24} width={w:<4}  ->  {full}")

    for root in roots:
        paths = Dot_Preprocess.find_paths(graph, root)

    Features = Dot_Preprocess.extract_dot_features(graph, nodes, indegree, outdegree, node_attrs, key_nodes)

    sig_key_str = ''
    if os.path.exists(vcd_pkl_file):
        print(f"Loading cached VCD object from: {vcd_pkl_file}")
        with open(vcd_pkl_file, 'rb') as f_cache:
            vcd = pickle.load(f_cache)
    else:
        print(f"Parsing VCD file: {vcd_file} (this may take a while)...")
        vcd = VCDVCD(vcd_file, store_tvs=True)
        with open(f"../data/{sys.argv[1]}/{sys.argv[1]}_vcd_signals.txt", "w") as f:
            for sig_key in vcd.signals:
                f.write(f"{sig_key}\n")
                sig_key_str += f"{sig_key}\n"
        with open(vcd_pkl_file, 'wb') as f_cache:
            pickle.dump(vcd, f_cache)
        print(f"Saving parsed VCD object to cache: {vcd_pkl_file}")

    if len(sys.argv) == 4:
        Vcd_Preprocessing.extract_vcd_features(Features, node_attrs, vcd, sys.argv[1])
    else:
        Vcd_Preprocessing.extract_vcd_features(Features, node_attrs, vcd, sys.argv[1], mode="train")

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
                # if str(node).__contains__("IN"):
                #     continue
                row = {"node": node}
                row.update(feats)
                writer.writerow(row)

        print(f"[INFO] Features written to {out_csv}")

    feature_names = ['Degree', 'Hamming distance', 'Paths', 'and', 'mux', 'or', 'xor']

    if len(sys.argv) == 4:
        Label_Preprocessing.label(Features, sys.argv[3])
        dump_features_to_csv(Features, f"../test/{sys.argv[3]}_features.csv")
        edge_file = f"../test/{sys.argv[3]}_edges.csv"
    else:
        Label_Preprocessing.label(Features,"train")
        dump_features_to_csv(Features)
        edge_file = f"../out/edges.csv"

    with open(edge_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "target"])
        writer.writeheader()
        for src, dst in edges:
            writer.writerow({"source": Features[src]["node_number"], "target": Features[dst]["node_number"]})
        print(f"[INFO] Edges written to {edge_file}")