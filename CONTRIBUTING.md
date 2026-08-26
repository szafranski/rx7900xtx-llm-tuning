# Contributing

The most useful thing anyone can add is a reproduction on a different card.
Everything here is one sample from one machine, which is the main thing limiting
what it can claim.

A reproduction report is worth reading if it states:

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
