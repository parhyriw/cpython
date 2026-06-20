import sys

import matplotlib.pyplot as plt
import numpy as np

if len(sys.argv) < 2:
    print("Usage : python results.py results/results_time.txt")
    exit()
filename = sys.argv[1]


def get_time(line: str) -> float:
    return float((line.split(":")[0]).split(" ")[-1])


print(f"Processing {filename}")
timings = []
with open(filename) as file:
    content = file.readlines()
    for i in range(len(content) // 2):
        timings.append(get_time(content[2 * i + 1]) - get_time(content[2 * i]))

arr = np.array(timings)

print("p50:", np.percentile(arr, 50))
print("p95:", np.percentile(arr, 95))
print("p99:", np.percentile(arr, 99))
print("max:", arr.max())
plt.figure(figsize=(8, 5))
plt.hist(arr, bins=500)
plt.xlabel("Stop-the-world duration (seconds)")
plt.ylabel("Frequency")
plt.title("STW Pause Time Distribution")
plt.grid(True, alpha=0.3)

plt.show()
