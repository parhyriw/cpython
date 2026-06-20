#!/usr/bin/env bash
perf script > "benchmark/results/results_$(date +%Y%m%d_%H%M%S).txt"
