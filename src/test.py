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

leaky_module = {
    "AES_PPRM1": ["SBOX", "Mixcolumns", "MX"],
    "AES_PPRM3": ["Sbox", "Mixcolumns", "MX"],
    "AES_TBL": ["SBOX", "Mixcolumns", "MX"],
    "RSA": ["MODEXP_SEQ", "MULT_BLK"],
    "SABER": ["PMULTs"]
}

results = []

for base, ffeat, fedge in paired:
    test_nodeset = pd.read_csv(ffeat)
    test_edge = pd.read_csv(fedge)
    keywords = leaky_module.get(base, [])
    def contains_any(value, keywords):
        return any(kw in str(value) for kw in keywords)
    test_nodeset["label"] = test_nodeset["node"].apply(
        lambda x: 1 if contains_any(x, keywords) else 0
    )
    test_nodeset.to_csv(ffeat, index=False)

    (X, edges, edges_weights), feature_names, num_features, num_classes, test_nodeset = graph_information(ffeat, fedge)
    Y = test_nodeset["label"]

    model = GNNNodeClassifier(
        graph_info=(X, edges, edges_weights),
        num_classes=num_classes,
        hidden_units=hidden_units,
        dropout_rate=dropout_rate,
        name="gnn_model",
    )

    # model(tf.convert_to_tensor([0], dtype=tf.int32))

    all_idx = tf.range(X.shape[0], dtype=tf.int32)
    probs = model(all_idx).numpy()
    model.load_weights("../out/gnn_weights.weights.h5")

    if probs.shape[1] == 2:
        y_pred = probs.argmax(axis=1)
        score_for_pos = probs[:, 1]
    else:
        y_pred = (probs.squeeze(-1) >= 0.5).astype(np.int32)
        score_for_pos = probs.squeeze(-1)

    y_true = Y.argmax(1) if Y.ndim == 2 else Y

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