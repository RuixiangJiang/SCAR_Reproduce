import pandas as pd
import tensorflow as tf


def graph_information(node_file, edge_file, mode):
    nodeset = pd.read_csv(node_file)
    df = pd.read_csv(edge_file)

    class_values = sorted(nodeset["label"].unique())
    class_idx = {name: id for id, name in enumerate(class_values)}
    paper_idx = {name: idx for idx, name in enumerate(sorted(nodeset["node_number"].unique()))}

    nodeset["node_number"] = nodeset["node_number"].apply(lambda name: paper_idx[name])
    nodeset["label"] = nodeset["label"].apply(lambda value: class_idx[value])
    nodeset.to_csv(node_file, index=False)

    # feature_names = {'Degree', 'Hamming distance', 'Paths', 'and', 'mux', 'or', 'xor'}
    if mode == "train":
        feature_names = ['Degree', 'mux', 'xor', 'Paths', 'or', 'Hamming distance', 'and']
    else:
        feature_names = ['or', 'Degree', 'and', 'mux', 'xor', 'Paths', 'Hamming distance']
    print("feature names:", feature_names)
    num_features = len(feature_names)
    num_classes = len(class_idx)

    df["source"] = df["source"].apply(lambda name: paper_idx[name])
    df["target"] = df["target"].apply(lambda name: paper_idx[name])
    edges = df[["source", "target"]].to_numpy().T
    edge_weights = tf.ones(shape=edges.shape[1])

    node_features = tf.cast(
        nodeset.sort_values("node_number")[list(feature_names)].to_numpy(), dtype=tf.dtypes.float32
    )

    return (node_features, edges, edge_weights), feature_names, num_features, num_classes