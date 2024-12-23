import numpy as np
from scipy.stats import kurtosis
import random
import time
from sklearn.metrics import roc_auc_score, average_precision_score, roc_curve, auc
import pandas as pd
from scipy.stats import sem

# Random Histogram Tree Node
class Node:
    def __init__(self, data, height, max_height, seed, node_id):
        self.data = data  # Data at this node
        self.height = height  # Current depth of the tree
        self.max_height = max_height  # Maximum allowed height of the tree
        self.seed = seed  # Random seed for attribute selection
        self.attribute = None  # Split attribute
        self.value = None  # Split value
        self.left = None  # Left child
        self.right = None  # Right child
        self.node_id = node_id  # Unique node identifier

    def is_leaf(self):
        return self.left is None and self.right is None

def compute_kurtosis(data):
    data = np.asarray(data)
    kurtosis_values = np.zeros(data.shape[1])
    for feature_idx in range(data.shape[1]):
        feature_data = data[:, feature_idx]
        mean = np.mean(feature_data)
        variance = np.mean((feature_data - mean) ** 2)
        fourth_moment = np.mean((feature_data - mean) ** 4)
        kurtosis_value = fourth_moment / ((variance + 1e-10) ** 2)
        kurtosis_values[feature_idx] = np.log(kurtosis_value + 1)
    return kurtosis_values

def choose_split_attribute(kurt_values, random_seed):
    np.random.seed(int(random_seed))  # Ensure seed is an integer
    Ks = np.sum(kurt_values)
    r = np.random.uniform(0, Ks)
    cumulative = 0
    for idx, k_value in enumerate(kurt_values):
        cumulative += k_value
        if cumulative > r:
            return idx
    return len(kurt_values) - 1

def RHT_build(data, height, max_height, seed_array, node_id=1):
    node = Node(data, height, max_height, seed_array[node_id], node_id)
    if height == max_height or len(data) <= 1:
        return node

    kurt_values = compute_kurtosis(data)
    attribute = choose_split_attribute(kurt_values, node.seed)
    split_value = np.random.uniform(np.min(data[:, attribute]), np.max(data[:, attribute]))

    node.attribute = attribute
    node.value = split_value

    left_data = data[data[:, attribute] <= split_value]
    right_data = data[data[:, attribute] > split_value]

    node.left = RHT_build(left_data, height + 1, max_height, seed_array, node_id=2*node_id)
    node.right = RHT_build(right_data, height + 1, max_height, seed_array, node_id=(2*node_id)+1)
    return node

#I think we have to pay more attention to the node_id's here
def insert(node, instance, max_height, seed_array):
    if not node.is_leaf():
        kurt_values = compute_kurtosis(np.vstack((node.data, instance)))
        #new_attribute = choose_split_attribute(kurt_values, seed_array[node.height])
        new_attribute = choose_split_attribute(kurt_values, seed_array[node.node_id])  # Use the correct seed

        if node.attribute != new_attribute:
            # Attribute mismatch; rebuild subtree from this node
            #return RHT_build(np.vstack((node.data, instance)), node.height, max_height, seed_array, node_id=1)
            return RHT_build(np.vstack((node.data, instance)), node.height, max_height, seed_array, node_id=node.node_id)

        if instance[node.attribute] <= node.value:
            node.left = insert(node.left, instance, max_height, seed_array)
        else:
            node.right = insert(node.right, instance, max_height, seed_array)
    else:
        if node.height == max_height:
            node.data = np.vstack((node.data, instance))
        else:
            # Since the max height has not been reached, we can continue to build the tree
            #return RHT_build(np.vstack((node.data, instance)), node.height, max_height, seed_array, node_id=1)
            return RHT_build(np.vstack((node.data, instance)), node.height, max_height, seed_array, node_id=node.node_id)
    return node

def score_instance(tree, instance, total_instances):
    node = tree
    while not node.is_leaf():
        if instance[node.attribute] <= node.value:
            node = node.left
        else:
            node = node.right

    leaf_size = len(np.unique(node.data, axis=0))
    P_Q = leaf_size / total_instances
    anomaly_score = np.log(1 / (P_Q + 1e-10))
    return anomaly_score

class RandomHistogramForest:
    def __init__(self, num_trees, max_height, window_size, number_of_features):
        self.num_trees = num_trees
        self.max_height = max_height
        self.window_size = window_size
        self.forest = []
        self.seed_arrays = []
        self.reference_window = []
        self.current_window = []
        self.number_of_features = number_of_features

    def initialize_forest(self):
        self.forest = []
        # Maximum possible nodes in a full binary tree
        num_nodes = 2 ** (self.max_height + 1)
        # Each tree gets a seed array for all possible nodes
        self.seed_arrays = [np.random.randint(0, 10000, size=num_nodes) for _ in range(self.num_trees)]

        for i in range(self.num_trees):
            tree = RHT_build(np.empty((0, self.number_of_features)), 0, self.max_height, self.seed_arrays[i], node_id=1)
            self.forest.append(tree)

    def update_forest(self, instance):
        self.current_window.append(instance)

        if len(self.current_window) >= self.window_size:
            self.reference_window = self.current_window[-self.window_size:]
            self.current_window = []
            self.forest = []
            for i in range(self.num_trees):
                tree = RHT_build(np.array(self.reference_window), 0, self.max_height, self.seed_arrays[i], node_id=1)
                self.forest.append(tree)

        for i, tree in enumerate(self.forest):
            self.forest[i] = insert(tree, instance, self.max_height, self.seed_arrays[i])

    def score(self, instance):
        total_instances = sum(len(np.unique(tree.data, axis=0)) for tree in self.forest)
        return np.sum([score_instance(tree, instance, total_instances) for tree in self.forest])

def STREAMRHF(data_stream, max_height, num_trees, window_size, number_of_features):
    scores = []
    forest = RandomHistogramForest(num_trees, max_height, window_size, number_of_features)
    forest.initialize_forest()

    for idx, instance in enumerate(data_stream):
        forest.update_forest(instance)
        scores.append(forest.score(instance))
        if (idx + 1) % 10 == 0:
            print(f"Processed {idx + 1} instances...")

    return scores

# Example usage
# Set a seed for reproducibility

print("Starting...")

np.random.seed(42)

dataset_name = "magicgamma"
path = f"C:/Users/giova/Downloads/wetransfer_forstefan_2024-12-13_1400/forStefan/data/public/{dataset_name}.gz"
#path = f"C:/Users/aleja/OneDrive - Universidad Nacional de Colombia/Documentos/Institut Polytechnique de Paris/courses/P1/Data Streaming/project/actual code/datasets/forStefan/data/public/{dataset_name}.gz"
df = pd.read_csv(path)

labels = df['label'].to_numpy(dtype='float32')
data_stream = df.drop('label', axis=1).to_numpy(dtype='float32')
print("data: ", data_stream.shape)

shuffled_indices = np.random.permutation(len(data_stream))
data_stream = data_stream[shuffled_indices]
labels = labels[shuffled_indices]

# Parameters
max_height = 5
num_trees = 100
window_size = len(data_stream) // 100  # 1% of the data stream
print("Window size: ", window_size)

n_runs =   1# number of runs
ap_scores = []
execution_times = []

for i in range(n_runs):
    # Measure Execution Time
    start_time = time.time()

    # Run STREAMRHF
    anomaly_scores = STREAMRHF(data_stream, max_height, num_trees, window_size, data_stream.shape[1])

    end_time = time.time()
    execution_time = end_time - start_time
    execution_times.append(execution_time)

    # Calculate Average Precision Score
    ap_score = average_precision_score(labels, anomaly_scores)
    auc_score = roc_auc_score(labels, anomaly_scores)
    fpr, tpr, thresholds = roc_curve(labels, anomaly_scores)
    print(f"Run {i + 1}: AP = {ap_score:.4f}, Execution Time = {execution_time:.2f} seconds")
    print(f"AUC Score from sklearn: {auc_score:.4f}")
    print("AUC Score from paper:", auc(fpr, tpr))
    ap_scores.append(ap_score)

# Convert to arrays
ap_scores = np.array(ap_scores)
execution_times = np.array(execution_times)

# Compute means
mean_ap = np.mean(ap_scores)
mean_time = np.mean(execution_times)

# Compute standard errors
ap_sem = sem(ap_scores)
time_sem = sem(execution_times)

# 95% Confidence interval = mean ± 1.96 * SEM
confidence_level = 1.96
ap_ci = confidence_level * ap_sem
time_ci = confidence_level * time_sem

# Print Results
print(f"Over {n_runs} runs:")
print(f"AP: {mean_ap:.4f} ± {ap_ci:.4f} (95% CI)")
print(f"Execution Time: {mean_time:.2f} ± {time_ci:.2f} seconds (95% CI)")