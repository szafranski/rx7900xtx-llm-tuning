# How the numbers were produced

## Harness

One request driver (`scripts/measure.py`) issues requests against a local
`llama-server`, samples GPU telemetry from `sysfs` and `amd-smi` while the
request runs, and appends one JSON object per request to a `.jsonl` file. The
benchmark scripts in `scripts/` set up a GPU profile and a server configuration,
call the driver, and tear down.

Each record carries throughput, prompt and generated token counts, VRAM and GTT
usage, a telemetry block for prefill and one for decode (mean and max board
power, junction/edge/memory temperature, fan, busy percentage, mV, SCLK), and
the output hashes described in [output-stability.md](output-stability.md).
`data/README.md` lists the fields.

## Rules the runs follow

**A null pair in every sweep.** At least one comparison in each sweep is a
setting against itself. It must come out at zero. Without it we would have
reported a 0.95 W noise floor as a result; that is exactly what happened before
we added it.

**Same tokens or no energy-per-token comparison.** Joules per token is only
compared between configurations whose generated text is identical, verified by
hash. See the warning in [power-and-undervolt.md](power-and-undervolt.md).

**Cold perplexity before each soak.** Against a fixed reference value, with the
server stopped. A run that fails this gate is aborted rather than recorded.

**Junction guard.** Runs abort above a configured junction temperature, and the
abort marker is cleared in an `EXIT` trap so it cannot leak into the next run.

**`dmesg` checked before and after.** Any new `amdgpu` line fails the run.

**Applied values read back.** The driver accepts writes it does not honour. Every
profile change is verified by reading the value back, and the run aborts on a
mismatch. See the clamp described in
[power-and-undervolt.md](power-and-undervolt.md).

## Sample sizes

Small, and they vary by experiment. The manifest (`data/manifest.csv`) gives the
record count for every file, and the charts print theirs. Some comparisons are a
single run per configuration; those are labelled as such and are only used to
rank options, not to size the gap between them. The soak comparisons carry 6 and
11 requests.

Nothing here is a statistically designed experiment. It is a tuning log with the
raw data attached.

## Known weaknesses

- One card, one machine, one model. No silicon-lottery coverage.
- The quality gate saturates; see [context-and-quality.md](context-and-quality.md).
- The output gate compares response text, not token IDs or logits.
- The soak sequence comparison takes the shorter of the two sequences, so a
  truncated session passes.
- Several results depend on a `llama.cpp` fork and cannot be reproduced
  upstream; [setup.md](setup.md) says which.

## Reproducing

You need the model, `wikitext-2-raw/wiki.test.raw`, and the build in
[setup.md](setup.md).

The scripts resolve `prompts/`, `results/` and `logs/` relative to the current
working directory, not to their own location, and they write into `results/`
under the file names used in `data/`. They also expect the helper scripts beside
them on the path they are invoked from. So run them from a scratch directory
with everything linked into it:

```
mkdir -p run/results run/logs && cd run
ln -s ../scripts/* ../prompts .
./amdgpu-profile.sh apply                # or 'reset' to return to factory
WARIANT=oszczednosc SPEC=ngmapk ./soak-and-output-gate.sh 1800
```

Paths to the model and the built binaries are hardcoded near the top of each
script as `/home/user/llm/...` and need editing for your machine.

The scripts and their inline comments are in Polish. The `docs/` are the English
account.
