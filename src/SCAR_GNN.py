from GNN import *
from GraphInformation import *

feature_file = "../out/features.csv"
edge_file = "../out/edges.csv"

nodeset = pd.read_csv(feature_file)
nodeset["label"] = nodeset["node"].str.contains(r"(sbox|mixcolumn)",case=False, na=False).astype(bool) \
                   | nodeset["Node"].str.contains(r"(sbox|mixcolumn)",case=False, na=False).astype(bool)
nodeset.to_csv(feature_file, index=False)

graph_info, feature_names, num_features, num_classes, nodeset = graph_information(feature_file, edge_file)

train_data = nodeset.iloc[0:196]
test_data = nodeset.iloc[196:]

print(f"num_features: {num_features}, num_classes: {num_classes}")
print(f"feature_names: {feature_names}")

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

y_train1 = tf.keras.utils.to_categorical(y_train, num_classes=2)
y_test1 = tf.keras.utils.to_categorical(y_test, num_classes=2)

x_train = train_data.node_number.to_numpy()
history = run_experiment(gnn_model, x_train, y_train1)

x_test = test_data.node_number.to_numpy()
_, test_accuracy, precision, recall = gnn_model.evaluate(x=x_test, y=y_test1, verbose=0)
print(f"Test accuracy: {round(test_accuracy * 100, 2)}%")
print(f"Test precision: {(precision* 100)}%")
print(f"Test recall: {(recall * 100)}%")

gnn_model.save_weights("../out/gnn_weights.weights.h5")
print("Saved:", gnn_model.count_params(), "params")