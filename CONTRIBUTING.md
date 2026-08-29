# Contributing

This repository publishes measurements from one machine. It is not a results
database: reproductions are not collected in `data/` or aggregated with the
measurements here.

If you run any of this on another card, an issue describing what you got is
welcome. Such a report is easier to read if it states:

- The card, vBIOS version, driver and Mesa version, and kernel.
- The `llama.cpp` commit, whether it is upstream or a fork, and the cmake flags.
- The model file and its size or hash.
- The exact GPU profile: power cap, voltage offset, clock cap, ASPM.
- The raw `.jsonl`, not just a summary. Record counts matter.

If you are reporting on the output-stability gate specifically, say which
sequences you compared and how long each was. The gate takes the shorter of the
two, so a short session against a long reference is a prefix comparison, and the
report should say so.

Corrections to the write-up are welcome, particularly where a number is stated
more strongly than the data behind it supports. That failure mode is the one
this repository is most at risk of.

Before opening a pull request that touches `data/` or `charts/`, run
`scripts/check.sh`.
