from sklearn.model_selection import train_test_split

from GNN import *
from GraphInformation import *

feature_file = "../out/features.csv"
edge_file = "../out/edges.csv"

nodeset = pd.read_csv(feature_file)
if not "label" in nodeset.columns:
    nodeset["label"] = nodeset["node"].str.contains(r"(sbox|mixcolumn)",case=False, na=False).astype(int)
nodeset.to_csv(feature_file, index=False)

graph_info, feature_names, num_features, num_classes, nodeset = graph_information(feature_file, edge_file)

import pickle
with open("../out/train_graph_info.pkl", "wb") as f:
    pickle.dump(graph_info, f)

# majority = nodeset[nodeset["label"] == 0]
# minority = nodeset[nodeset["label"] == 1]
# majority_downsampled = majority.sample(n=len(minority), random_state=42)
# balanced = pd.concat([majority_downsampled, minority])
# train_data, test_data = train_test_split(
#     nodeset,
#     test_size=0.2,
#     random_state=42,
#     shuffle=True
# )
# train_data = balanced.sample(frac=1, random_state=42)

train_data, test_data = train_test_split(
    nodeset,
    test_size=0.2,
    random_state=42,
    shuffle=True,
    stratify=nodeset["label"]
)

print(f"num_features: {num_features}, num_classes: {num_classes}")
print(f"feature_names: {feature_names}")

print("Train label distribution:")
print(train_data["label"].value_counts())

print("\nTest label distribution:")
print(test_data["label"].value_counts())

# Create train and test features as a numpy array.
x_train = train_data[list(feature_names)].to_numpy()
x_test = test_data[list(feature_names)].to_numpy()
# Create train and test targets as a numpy array.
y_train = train_data["label"]
y_test = test_data["label"]

baseline_model = create_baseline_model(hidden_units, num_classes, dropout_rate, num_features)
history = run_experiment(baseline_model, x_train, y_train)

gnn_model = GNNNodeClassifier(
    graph_info=graph_info,
    num_classes=num_classes,
    hidden_units=hidden_units,
    dropout_rate=dropout_rate,
    name="gnn_model",
)

y_train1 = y_train.to_numpy().astype("float32")
y_test1  = y_test.to_numpy().astype("float32")

x_train = train_data.node_number.to_numpy()
history = run_experiment(gnn_model, x_train, y_train1)

x_test = test_data.node_number.to_numpy()
_, test_accuracy, precision, recall = gnn_model.evaluate(x=x_test, y=y_test1, verbose=0)
print(f"Test accuracy: {round(test_accuracy * 100, 2)}%")
print(f"Test precision: {(precision * 100)}%")
print(f"Test recall: {(recall * 100)}%")

gnn_model.save_weights("../out/gnn_weights.weights.h5")
print("Saved:", gnn_model.count_params(), "params")

print("Test model loaded from weights")
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
model = GNNNodeClassifier(
    graph_info=graph_info,
    num_classes=num_classes,
    hidden_units=hidden_units,
    dropout_rate=dropout_rate,
    name="gnn_model",
)
_ = model.predict(tf.convert_to_tensor([0], dtype=tf.int32))
model.load_weights("../out/gnn_weights.weights.h5")
Y = nodeset["label"]
all_idx = nodeset.node_number
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
print(f"Result: Acc={acc:.4f}  F1={f1:.4f}  AUC={auc:.4f}")