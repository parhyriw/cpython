import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if len(sys.argv) < 2:
    print("Usage : python results.py results/results_time.txt")
    exit()
filename = sys.argv[1]


df = pd.read_csv(filename, header=None)


print(f"Processing {filename}")


stw = np.array(df[0])
stw = stw/1E9
gc = np.array(df[1])
gc = gc/1E9

view = stw
print("p50:", np.percentile(view, 50))
print("p95:", np.percentile(view, 95))
print("p99:", np.percentile(view, 99))
print("max:", view.max())
plt.figure(figsize=(8, 5))
plt.hist(view, bins=500)
plt.xlabel("Durée de syncronisation des fils (s)")
plt.ylabel("Nombre de syncronisations")
plt.title("")
plt.grid(True, alpha=0.3)

plt.savefig("benchmark/results/graph2.png")
plt.show()
