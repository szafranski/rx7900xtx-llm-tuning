# Context length, output quality and the vision projector

## Context profiles

At a 32K context with `q8_0` KV cache, decode ran at about 70 tok/s across a
wide parameter sweep, against 35.18 tok/s with speculation disabled
(`data/context-32k.jsonl`).

At 128K the cache type is what matters
(`data/context-128k-cache-types.jsonl`, one run each, 92K-token prompt):

| KV cache | decode | VRAM |
|---|---|---:|---:|
| `q8_0` / `q8_0` | 53.13 tok/s | 22945 MiB |
| `q8_0` / `turbo4` | 52.31 tok/s | 21751 MiB |
| `q8_0` / `q8_0` + projector | 53.02 tok/s | 23833 MiB |

`turbo4` gives up 1.5 percent of throughput and saves 1194 MiB, which is what
makes a 128K context fit alongside the vision projector on a 24 GB card. It is
a fork-only cache type; see [setup.md](setup.md).

A needle-retrieval check at 93 percent of the context window passed in every
variant, including with the projector loaded (`data/context-128k.jsonl`).

## A closer look at `turbo4` against `q8_0` at 128K

The table above compares the two cache types on speed and VRAM. It does not
say whether they compute the same thing. This section is a second round aimed
at that question, run at `--ctx-size 131072` on both variants with everything
else held fixed. Scripts are `scripts/kv_run_*.py` against
`scripts/srv-kv-128k.sh`; every figure below is reproduced by
`scripts/kv_distribution.py`.

### How the comparison is measured

Each variant was asked for a single next token with `temperature 0`, `top_k 1`,
`top_p 1`, a fixed seed, and `logprobs` with `top_logprobs: 20`, over prompts
frozen to disk so both variants read byte-identical input. The distance between
two runs is half the L1 distance over the union of the two reported top-20
lists, with a token absent from one list counted as probability zero.

**This is a truncated total variation distance, not the real one.** The server
reports 20 entries out of a 150K vocabulary, so the tail is unknown. What makes
the figure usable is that the reported entries capture at least 0.99995 of the
distribution in every cell (the captured mass is printed by the script), so the
true TVD cannot differ from the quoted one by more than about 4e-5. Any
difference at or below that size is truncation error, not signal.

### Neither cache type is deterministic

Four full recomputes of the same 64K prompt inside one server instance, same
metric, all six pairs:

| V cache | min | median | max | first-token logprob range |
|---|---:|---:|---:|---:|
| `q8_0` | 0.000000 | 0.001479 | 0.001658 | 0.001696 |
| `turbo4` | 0.003159 | 0.008324 | 0.014445 | 0.014879 |

Both wobble; `turbo4` wobbles more. We are deliberately not turning that into a
"Nx noisier" headline, because it is a ratio of two four-run ranges and n=4
bounds nothing. Read it as: on this machine `q8_0`'s repeat spread was under
0.002 and `turbo4`'s reached 0.014, with no overlap between the two sets of six
pairs.

Two repeats of an 8K prompt served from a warm prompt cache came back at
distance 0 in both variants. A null pair that easy is not a floor, which is why
the four-recompute measurement above exists.

### The difference between the variants is inside that spread

One full recompute per variant per length, `cache_prompt` off:

| context | truncated TVD | p(top-1) `q8_0` | p(top-1) `turbo4` | top-1 token |
|---|---:|---:|---:|---|
| 8K | 0.000005 | 0.99999 | 0.99998 | `The` |
| 32K | 0.000707 | 0.98699 | 0.98770 | `The` |
| 64K | 0.010877 | 0.96523 | 0.97609 | `The` |
| 120K | 0.001635 | 0.94046 | 0.94199 | `The` |

The 64K cell is the only one worth comparing against the repeat measurement,
because that is the length the repeats were run at: 0.010877 sits inside
`turbo4`'s own range of 0.003159 to 0.014445. The 8K figure, 0.000005, is below
the truncation bound and means nothing beyond "no difference we can see". The
top-1 token is the same in all eight cells, and the difference does not grow
with context length.

The column that does move monotonically is confidence: p(top-1) falls from
0.99999 to 0.94 as the context grows, by almost the same amount in both
variants. That is the model getting less certain with more context in front of
it, not a cache error.

### Prompt-cache reuse moves the distribution, in both variants

Answering the same 64K prompt from a half-cached prefix instead of recomputing
it shifts the next-token distribution by 0.007052 in `q8_0` and 0.007391 in
`turbo4`. The absolute figures are within 5 percent of each other, so this is a
property of llama.cpp's cache-reuse path and not of the cache type. It is
larger than `q8_0`'s entire repeat spread and inside `turbo4`'s, which means the
same mechanism is visible over one variant's noise and buried in the other's.

Worth knowing if you compare hashes across runs: whether a prompt was served
from cache changes the result more reliably than which of these two cache types
you picked.

### Retrieval and vision: both at the ceiling

A 160-cell needle matrix on `turbo4` (four lengths x five relative positions x
eight keys, `data/kv-needles-turbo4.json`) scored 160/160. **That is a ceiling
and it decides nothing.** We did not run it on `q8_0`, because a test that
cannot fail cannot discriminate. Two further weaknesses, for anyone reusing
`scripts/kv_run_needles.py`: the keys are a deterministic function of their
position, so the answer is inferable from the scheme without finding the
needle, and there are no near-miss distractor keys, so the task is lexical.

Three image tasks passed in both variants (`data/kv-vision-*.json`, inputs in
`data/kv-vision-img/`). Two of the three produced identical response hashes
across variants; the third differed in wording and was correct in both. Three
tasks is a smoke test.

Both of these ran with `enable_thinking: false` per request, while the shipped
profile runs reasoning on. The deviation was applied identically to both
variants, so it does not bias the comparison, but it does mean these numbers
are not the accuracy a user of the shipped profile would see.

### VRAM headroom is the actual argument

At `--ctx-size 131072` with the draft model loaded:

| V cache | KV buffers, main + draft | VRAM headroom under a 120K prefill |
|---|---:|---:|
| `q8_0` | 4352 + 272 = 4624 MiB | 367 MiB |
| `turbo4` | 3232 + 202 = 3434 MiB | about 1.6 GB |

`q8_0` fits, with 367 MiB to spare. That is a binary risk, not a gradual one:
one more resident buffer and the server fails to start rather than running
slightly worse. Given that the quality difference sits inside the run-to-run
spread, the 1190 MiB is the reason to pick `turbo4` here, and the reason not to
is that its wider spread makes it the worse choice if you want output hashes to
be your regression signal.

Nothing spilled to system RAM in either variant: 66 of 66 layers on the GPU, all
KV on `Vulkan0`, and `RADV_PERFTEST=nogttspill` set so an over-allocation fails
instead of spilling. The GTT arithmetic behind that is in
[data/README.md](../data/README.md#gtt-at-128k).

Prefill throughput falls with context on both: 694 tok/s at 8K, 311 tok/s at
120K. Attention cost, and it happens equally in both variants.

### What this section does not establish

- One card, one model, one fork build, one set of prompts. The transferable
  number is roughly the KV allocation saving for the same model and context;
  nothing here predicts that 128K fits on someone else's card.
- Next-token distributions and single-field answers only. Nothing about long
  free-form output, which is where a subtle difference would show.
- `q8_0` is the reference here, not ground truth. There is no unquantized-KV
  baseline at this context length, so both figures are relative.
- The comparison detects differences larger than the run-to-run spread. It did
  not detect one, which is not the same as there being none.

## The quality gate hit its ceiling

22 tasks with a single unambiguous correct answer, generated over a synthetic
50K-token corpus, run across every configuration variant: 132 correct answers,
zero errors. A harder variant of the same set behaved the same way.

**This is a ceiling, not a result.** A gate that scores full marks in every
condition has no power to discriminate between them. It rules out a gross
regression on this task type and nothing more. In particular it does not show
that long free-form output is unchanged, which is the case where a subtle
quality difference would actually show up. Data: `data/quality-keyed.jsonl`,
`data/quality-keyed-hard.jsonl`, keys in `data/quality-keys*.json`, scoring in
`scripts/score_quality.py`.

The corpus and questions are generated by `scripts/gen_quality_corpus.py` and
are synthetic. No third-party text is redistributed here.

## Reasoning effort

`medium` improved the tokens-per-second counter (70.03 to 72.87 in English,
76.20 in Polish; `data/context-32k.jsonl`) and cost 2.7x to 4.8x more energy per
answer, because it generates a great deal more. The reasoning budget is the
largest single cost lever in the configuration. Budget 2048 and 8192 were
indistinguishable on these questions, because neither was reached.

The full table is in
[power-and-undervolt.md](power-and-undervolt.md#energy-per-token-is-the-wrong-metric-when-the-setting-changes-the-token-count).

## Vision projector

`data/projector-q8-vs-bf16.jsonl`, three image tasks against two projector
builds:

| projector | VRAM | pl-doc | pl-tabela | pl-wykres |
|---|---:|---:|---:|---:|
| Q8_0 | 21065 MiB | 72.09 | 84.56 | 82.72 |
| BF16 | 21393 MiB | 69.20 | 84.75 | 82.54 |

BF16 costs 328 MiB and is not faster. Both answered all three tasks. Three
tasks is not a quality evaluation, so the claim here is narrow: we found no
reason to pay the 328 MiB.

Further image runs under the shipped profile are in `data/vision.jsonl` and
`data/idle-with-projector.jsonl`.
