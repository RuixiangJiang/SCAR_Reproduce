import os, glob
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from GNN import *
from GraphInformation import *

TEST_DIR = "../test"

feature_files = sorted(glob.glob(os.path.join(TEST_DIR, "*_features.csv")))
paired = []
for fpath in feature_files:
    base = os.path.basename(fpath).replace("_features.csv", "")
    epath = os.path.join(TEST_DIR, f"{base}_edges.csv")
    if os.path.exists(epath):
        paired.append((base, fpath, epath))

if not paired:
    print("No dataset pairs found under ./test (expect *_features.csv + *_edges.csv)")
else:
    print(f"Found {len(paired)} dataset(s):", [b for b,_,_ in paired])

results = []

for base, ffeat, fedge in paired:
    print(f"Testing {base}: read {ffeat} and {fedge}")

    (X, edges, edges_weights), feature_names, num_features, num_classes, test_nodeset = graph_information(ffeat, fedge)
    Y = test_nodeset["label"]

    import pickle
    with open("../out/train_graph_info.pkl", "rb") as f:
        train_graph_info = pickle.load(f)

    model = GNNNodeClassifier(
        graph_info=(X, edges, edges_weights),
        num_classes=num_classes,
        hidden_units=hidden_units,
        dropout_rate=dropout_rate,
        name="gnn_model",
    )
    _ = model.predict(tf.convert_to_tensor([0], dtype=tf.int32))
    model.load_weights("../out/gnn_weights.weights.h5")

    all_idx = test_nodeset.node_number
    probs = model.predict(all_idx.to_numpy(dtype="int32"), verbose=0)  # (N,1)
    y_pred = (probs.squeeze(-1) >= 0.5).astype(int)
    score_for_pos = probs.squeeze(-1)
    y_true = Y if Y.ndim == 1 else Y.argmax(1)  # 0/1

    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred)
    try:
        auc = roc_auc_score(y_true, score_for_pos)
    except Exception:
        auc = float('nan')

    results.append((base, acc, f1, auc))

    test_nodeset["prediction"] = y_pred
    test_nodeset.to_csv(ffeat + "_pred.csv", index=False)

for (base, acc, f1, auc) in results:
    print(f"for {base}: Acc={acc:.4f}  F1={f1:.4f}  AUC={auc:.4f}")