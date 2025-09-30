import pandas as pd
import tensorflow as tf

def graph_information(node_file, edge_file):
    nodeset = pd.read_csv(node_file)
    # if "node" in nodeset.columns:
    #     nodeset.drop(["node", "Node"], axis=1)
    nodeset = nodeset.reindex(columns=['node_number', 'Node', 'Degree', 'Hamming distance', 'Paths', 'and', 'mux', 'or', 'xor', 'label'])
    nodeset.to_csv(node_file, index=False)
    df = pd.read_csv(edge_file)

    class_values = sorted(nodeset["label"].unique())
    class_idx = {name: id for id, name in enumerate(class_values)}

    feature_names = ['Degree', 'Hamming distance', 'Paths', 'and', 'mux', 'or', 'xor']
    num_features = len(feature_names)
    num_classes = len(class_idx)
    node_features = tf.cast(
        nodeset[feature_names].to_numpy(), dtype=tf.dtypes.float32
    )
    edges = df[["source", "target"]].to_numpy().T
    edge_weights = tf.ones(shape=edges.shape[1])

    return (node_features, edges, edge_weights), feature_names, num_features, num_classes, nodeset