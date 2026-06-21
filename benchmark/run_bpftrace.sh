#!/usr/bin/env bash
bpftrace -c "./python benchmark/stress.py" -e '
uprobe:./python:stop_the_world.lto_priv.0
{
    @stw_start[tid] = nsecs;
}

uretprobe:./python:stop_the_world.lto_priv.0
/@stw_start[tid]/
{
    @stop_end[tid] = nsecs;
    @stw_dur[tid] = nsecs - @stw_start[tid];
    delete(@stw_start[tid]);
}

uprobe:./python:start_the_world.lto_priv.0
/@stop_end[tid]/
{
    printf("%llu,%llu,%d\n",
           @stw_dur[tid],
           nsecs - @stop_end[tid],
           tid);

    delete(@stw_dur[tid]);
    delete(@stop_end[tid]);
}
' > benchmark/results/stw.csv
# Manual cleanup of stw.csv needed
