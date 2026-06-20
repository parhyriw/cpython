#!/usr/bin/env bash
perf record -e probe_python:stop_the_world_lto_priv_0 -e probe_python:start_the_world_lto_priv_0 ./python $1
