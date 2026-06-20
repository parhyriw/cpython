#!/usr/bin/env bash
perf probe -x ./python start_the_world.lto_priv.0
perf probe -x ./python stop_the_world.lto_priv.0
