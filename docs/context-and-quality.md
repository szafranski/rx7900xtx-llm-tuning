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
`scripts/srv-kv-128k.sh`. Every distribution figure below is reproduced by
`scripts/kv_distribution.py`; the memory and throughput figures at the end of the
section come from the server startup log excerpted in
`data/kv-startup-128k.log`.

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

Two full recomputes of an 8K prompt, prompt cache off, came back at distance 0
in both variants, and repeats served from a warm cache did the same. Neither is
a floor: the spread only appears at longer contexts, which is why the
four-recompute measurement above was run at 64K.

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
variants. That is this prompt's top-1 probability falling as the context in front of it
grows, by almost the same amount in both variants, rather than a cache error. It
is one prompt, so it says nothing about how confidence behaves in general.

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
cannot fail cannot discriminate. Its replacement, which does discriminate, is
[the next section](#a-long-context-test-that-is-not-at-the-ceiling). Two further weaknesses, for anyone reusing
`scripts/kv_run_needles.py`: the keys are a deterministic function of their
position, so the answer is inferable from the scheme without finding the
needle, and there are no near-miss distractor keys, so the task is lexical.

Three image tasks passed in both variants (`data/kv-vision-*.json`, inputs in
`data/kv-vision-img/`). Two of the three produced identical response hashes
across variants; the third differed in wording and was correct in both. Three
tasks is a smoke test.

The needle matrix ran with `enable_thinking: false` per request, while the
shipped profile runs reasoning on; the vision cases did not set the flag and so
ran as the profile does. The deviation was applied identically to both variants,
so it does not bias the comparison between them, but it does mean the needle
figures are not the accuracy a user of the shipped profile would see.

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
instead of spilling. Roughly 1 GB does sit in GTT, and it is the host buffers
`llama-server` allocates regardless; the arithmetic, including the 6 MiB it does
not account for, is in [data/README.md](../data/README.md#gtt-at-128k).

Prefill throughput falls with context on both: 689 tok/s at 8K and 311 tok/s at
120K with `q8_0`, 695 and 306 with `turbo4`, on prompts of 7948 and 120017
tokens (`data/kv-startup-128k.log`). Attention cost, and it happens to much the
same degree in both.

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

## A long-context test that is not at the ceiling

The needle matrix above scored 160/160 and settled nothing. This is the replacement,
run on both cache types at `--ctx-size 131072`. Generator
`scripts/kv_gen_longctx.py`, runner `scripts/kv_run_longctx.py`, results in
`data/kv-longctx-{q8,turbo4}.json`, questions and answers in
`data/kv-longctx-items.json`.

131 fact lines and 24 questions, **identical at every context length**; only the
filler around them scales, so the single variable is how much context the facts
are spread through. Every fact uses the same two sentence shapes, so no line
stands out from the others:

- **A, retrieval among near misses.** Name the partition of a given key. The
  context also holds three keys differing from it by one character, each with a
  different partition, so matching on appearance gives a confident wrong answer.
- **B, two hops.** Key to partition in the first 30 percent of the context,
  partition to node in the last 30 percent. Maps for the near-miss keys'
  partitions are present too, so a slip on the first hop produces a plausible
  node.
- **C, aggregation.** Count 3 to 7 entries of one partition, scattered across the
  whole context.

Eight items per type, two passes, four lengths: 192 queries per variant. Keys are
random, not derived from position, which was a defect of the needle matrix.

### The window is not usable to the same degree for every task

`turbo4`, correct out of 16 per cell:

| task | 8K | 32K | 64K | 120K |
|---|---:|---:|---:|---:|
| A retrieval | 16 | 16 | 16 | 14 |
| B two hops | 12 | 10 | 10 | 6 |
| C aggregation | 10 | 8 | 2 | 0 |
| total of 48 | 38 | 34 | 28 | 20 |

`q8_0` on the same items: 40 / 32 / 28 / 20, and identical per type.

At 120K, direct key retrieval held at 14 of 16 while two-hop retrieval fell to 6
and counting reached 0. **Every counting error in both variants is an
undercount, never an overcount** - in these greedy runs. The reasoning-arm
section below repeats the counting items with the shipped profile's sampling and
records one overcount there, so the direction is a property of what was measured
here, not of the model. The follow-up test in the next section shows
that this does not mean the entries were missed: asked to list them instead, the
model usually names the complete set and still reports a smaller number. With
reasoning off and a bare-number response format, a wrong count carries no
visible intermediate step, so nothing about its mechanism can be read off the
count alone.

Eight unique items per type per length is a small sample and the reading should
stay narrow: this is what these tasks did on this corpus, not a general
statement that 128K is usable for retrieval and unusable for aggregation. What
it does establish is that a single needle-retrieval pass is the wrong instrument
for the question. Retrieval is the part that survives; measuring only retrieval
is how a long-context check reports 160/160 and tells you nothing.

### Counting fails while enumeration mostly works

The 0 of 16 above invites the reading that the entries were out of reach at
120K. They were not. The same type C items were re-run asking two questions per
item in the same session: first the phase-4 wording (`ile kluczy nalezy do
partycji P` - how many keys belong to partition P), then a request to list them.
One cache type (`turbo4`), 64K and 120K, two passes, eight items: 64 queries.
Runner `scripts/kv_run_enumerate.py`, results
`data/kv-enumerate-turbo4.json`. The answer keys were re-derived by regex from
the frozen context files rather than taken from the generator's metadata, and
the script aborts unless the two lengths yield identical key sets that also
match the generator.

| | 64K | 120K |
|---|---:|---:|
| count correct | 2/16 | 0/16 |
| list complete | 11/16 | 10/16 |
| keys recalled | 0.929 (65/70) | 0.914 (64/70) |
| keys invented | 0 | 0 |
| list complete **and** count wrong | 11/16 | 10/16 |
| list incomplete and count wrong | 3/16 | 6/16 |

At 120K the context held 70 keys across the eight items; the model named 64 of
them and counted 52. Its count did not even match the length of its own list:
`count == len(list)` in 3 of 16 at 64K and 6 of 16 at 120K, and at 120K the
count was below its own list ten times and above it never. No key was invented
in any of the 32 items. All 30 wrong counts undercount, by 1.12 keys on average
at both lengths, greedy throughout.

The count accuracy came out 2/16 at 64K and 0/16 at 120K, which is exactly what
type C scored in the matrix above, from a separate server start on a separate
run. Repeat disagreement was 0 of 8 items for the count at both lengths, and 1
of 8 at 64K and 0 of 8 at 120K for the list.

Requesting the keys and counting them client-side is a strong mitigation where
the returned list is complete: it would lift 2 of 32 correct counts to 21 of 32
here. It is not a prompt-level fix for the limitation, because it leaves the 11
incomplete lists untouched, and a recall of 0.91 is not 1.0 - some entries are
genuinely lost. The honest summary is that on this corpus counting is wrong
essentially always while these runs recalled 91 percent of the entries.

#### The pair order was a real confound, and it was measured

The list was always the second question of the pair above. Each request is a
standalone completion carrying no conversation history, and both questions read
the same cached prefix, but the server runs `--spec-type draft-mtp,ngram-map-k`
and its n-gram map does persist across requests, so the two positions were not
provably equivalent. The whole set was re-run with the list asked first
(`data/kv-enumerate-turbo4-listfirst.json`, same runner with the pair flag
`LN`).

| | 64K count-first | 64K list-first | 120K count-first | 120K list-first |
|---|---:|---:|---:|---:|
| count correct | 2/16 | 2/16 | 0/16 | 2/16 |
| list complete | 11/16 | 14/16 | 10/16 | 10/16 |
| keys recalled | 0.929 | 0.971 | 0.914 | 0.914 |

Order does matter, and it worked against the first run rather than for it: at
64K the list came out better when asked first, 14 of 16 complete against 11,
and three items changed their list. At 120K no list changed and two counts did.
So the enumeration figures in the table above are, if anything, understated.

Pooling both orders sharpens the central claim instead of weakening it: across
all 64 items there are **45 cases where the list was complete, and the count was
correct in none of them**. All six correct counts in the whole set occurred on
items where the list was incomplete. Counting and enumeration are not two views
of one retrieval: on this corpus they dissociate, and getting the count right
was never a consequence of having the entries. Note the direction, because it is
not independence - every correct count sat on an incomplete list, so the two are
associated, just not in the way a shared-retrieval account would predict.

What this does not establish: that the mechanism is general rather than specific
to these items, that the cache type has anything to do with it, that a list
always rescues a count, or that eight items scale to a rate. The disabled
reasoning does turn out to matter, and by more than anything else measured here;
that is the next section.

### The two cache types score the same

| | `q8_0` | `turbo4` |
|---|---:|---:|
| A | 62/64 | 62/64 |
| B | 38/64 | 38/64 |
| C | 20/64 | 20/64 |
| total | 120/192 | 120/192 |

Matched item by item, 7 of 192 answers differ between the variants. Six are type
C off by one, one is a type B naming a different node, and they cancel: per
length `q8_0` scored 40/32/28/20 against `turbo4`'s 38/34/28/20.

The floor to read that against is the same variant answering the same item
twice: `turbo4` disagreed with itself on 0 of 96 positions, `q8_0` on 1 of 96.
Like for like that is 3.6 percent of answers differing between the variants
against 0 and 1.0 percent within them, so something beyond the item is moving
individual answers. This design cannot say whether that something is the cache
type or the run order, which was reversed between the variants. What it can say
is that it has no direction: on this benchmark `turbo4` shows no accuracy cost
against `q8_0`.

That the repeats are nearly deterministic is worth stating plainly, because it
cuts both ways: it makes the floor tight, and it means the second pass is
mostly a reproducibility check rather than independent evidence. The effective
sample is closer to eight items per cell than sixteen.

### Conditions, including the awkward ones

- Both variants read byte-identical prompts, frozen to disk with SHA-256
  recorded in each result file and verified equal across the two runs.
- All items ran on a shared warm prompt prefix, one prefill per length. The
  previous section shows cache reuse itself moves the distribution; the
  condition is the same for both variants, but it is not a cold-cache result.
- `enable_thinking: false` per request, while the shipped profile runs reasoning
  on. These accuracies are not what the shipped profile would produce.
- Run order was counterbalanced, `turbo4` ascending and `q8_0` descending. That
  removes a shared drift but **confounds variant with order**: the two-point
  crossovers at 8K and 32K could be order, item-level counting variation, or
  noise, and this design cannot separate them. Each variant ran in one order
  only, so there is no order control here; the two orders reached the same
  total, which is all that can be said.
- One card, one model, one build, one generated corpus. The test can only detect
  a difference larger than its own resolution, and eight unique items per cell
  is a coarse resolution. It did not find one.

### Reasoning on: the errors above do not appear at all

Every accuracy in this whole section was measured with `enable_thinking: false`,
while the shipped profile runs reasoning on. That makes the numbers above a
statement about a configuration nobody here actually serves, so the counting and
two-hop items were re-run at 120K with both arms on one server.

The server carries the **shipped** profile this time, not a comparable-to-earlier
baseline: sampling `--temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05`,
`--cache-reuse 256`, `--reasoning-effort medium`, `--reasoning-budget 8192`
(`scripts/srv-kv-reasoning.sh`). One thing about that flag is worth knowing before
reading the table: `--reasoning-effort medium` puts **no instruction at all**
into the prompt - it renders byte for byte like passing no level, as the next
section shows. So this arm is reasoning with no effort instruction, not
reasoning turned down. External validity to the deployed profile was
chosen over comparability with the greedy phases, so the earlier 0/16 is not a
control for this - the `off` arm below is. Eight type B and eight type C items,
four repeats, both arms per item, arm order alternating between repeats,
seed `1000*rep+i`: 128 queries. Only `content` is scored; the reasoning trace is
not. Runner `scripts/kv_run_reasoning.py`, results `data/kv-reasoning-120k.json`.

| arm | type | correct | median latency | median output tokens |
|---|---|---:|---:|---:|
| reasoning off | B two-hop | 11/32 | 3.7 s | 8 |
| reasoning off | C counting | 8/32 | 3.5 s | 2 |
| reasoning on | B two-hop | 32/32 | 8.6 s | 179 |
| reasoning on | C counting | 32/32 | 60.7 s | 2554 |

**64 of 64 against 19 of 64.** Not one error survived in the reasoning arm, on
either question type. Nothing else measured on this card moves a quality number
by that much.

The supporting readings are all clean. Zero truncations in 128 queries, so the
operational reading (a truncation counts as a failure) and the conditional one
(only finished answers) are the same table. Zero non-bare answers, so the
grading trap that a prose reply would have sprung - `partycja 77 ma 5 kluczy`
scored as 77 - never fired; the model answered with the bare value every time.
Position within the pair had no effect: 10/32 against 9/32 in the `off` arm,
32/32 in both positions in the `on` arm. The `off` arm also replicates phase 4
on the two-hop items, 34.4 percent here against 37.5 percent there, which is the
one thing here that behaves as a control should.

The cost is the whole trade. A counting answer's median goes from 3.5 s to
60.7 s, 17.3x, and from 2 output tokens to 2554 - of which effectively all are
reasoning, since the answer itself is one character. The longest single answer
used 3532 tokens. That is 43 percent of the 8192-token budget, so the budget was
comfortable for everything asked: no answer was cut off and the worst case left
4660 tokens unused.

What this does and does not license. It is accurate that **no error occurred**
in the reasoning arm on this material; it is not accurate to say reasoning fixes
counting. There are eight distinct questions per type, and the four repeats
measure decode stability, not material diversity - so for generalising to new
questions the effective n is 8, and 0 of 8 still admits a true error rate around
30 percent at 95 percent confidence. The repeat agreement in the `on` arm (0 of
16 items answered inconsistently, against 13 of 16 with reasoning off) is a
consequence of 64/64 and not independent evidence about sampling: with a single
unambiguous bare answer, every correct run necessarily agrees with every other.

Nor does this retire the client-side mitigation from the previous section. It
shows the shipped profile did not need it here, not that it is safe to drop for
new material, and the list-and-count route is 17x cheaper per answer. Untouched
entirely: other context lengths, other documents, whether the budget holds for
harder reasoning, and whether reasoning repairs the arithmetic or merely spends
enough tokens to work around it. The counting weakness documented above is real
for a reasoning-off client and was not reproducible with reasoning on.

### Effort `low` scores the same, costs a third as much, and does it unevenly

The arm above ran at `medium`. `low` is the only lower level the template
accepts, so the same 16 items, the same four repeats and the same seeds were
replayed with the level overridden per request. Same server, same frozen
material, same order - a paired comparison, one arm at a time for the reason the
next subsection gives. Runner `scripts/kv_run_effort_low.py`, results
`data/kv-effort-low-120k.json`.

| type | level | correct | median tokens | p90 tokens | max tokens | median latency | p90 latency |
|---|---|---:|---:|---:|---:|---:|---:|
| B two-hop | medium | 32/32 | 179 | 238 | 1215 | 10.1 s | 11.1 s |
| B two-hop | low | 32/32 | 181 | 222 | 1214 | 10.2 s | 11.0 s |
| C counting | medium | 32/32 | 2570 | 3416 | 3532 | 61.1 s | 95.1 s |
| C counting | low | 32/32 | 206 | 2660 | 2995 | 10.6 s | 63.9 s |

`low` matched `medium` exactly: 64 of 64, zero truncations, zero non-bare
answers, and no item answered inconsistently across its four repeats. Over the
64 pairs it used 29344 output tokens against 85330, **2.9x fewer**, and 17.5
minutes of wall clock against 39.0, **2.2x less**.

Three things the medians hide, and each one changes what the setting is worth.

**On two-hop retrieval the level does nothing.** 181 tokens against 179. At
`medium` the model already answers those items in under 200 tokens, so there is
no reasoning to shorten. The entire saving comes from the counting items.

**On counting, `low` is not shorter - it is bimodal.** The median is 206 tokens,
but 6 of 32 queries ran past 1000, up to 2995, which is what `medium` spends.
The long run is not a property of the question. Per item, across its four
repeats:

```
#16: [230, 198, 372, 372]      #20: [155, 144, 178, 181]
#17: [171, 171, 2772, 173]     #21: [2851, 220, 243, 207]
#18: [2504, 214, 204, 192]     #22: [2660, 449, 489, 2995]
#19: [177, 176, 179, 2615]     #23: [202, 181, 206, 204]
```

The same question enumerates the whole partition on one sample and answers in
200 tokens on the next, and both are correct. So the median latency drops
roughly 6x while the p90 stays at 63.9 s, and nothing in the request predicts
which path it will take. If what matters is a predictable answer time rather
than a cheap average one, `low` does not deliver it.

**In 20 of the 64 pairs `low` used no fewer tokens than `medium`**, and in three
it used far more: 1214 against 167 on a two-hop item, 2660 against 533 and 2504
against 1769 on counting items. "Keep your thinking brief" is a sentence in the
prompt, not a decode-time limit.

What this licenses is narrow. `medium` already scored 64/64 here, so this gate
is at its ceiling for both levels and a tie cannot separate them - the honest
reading is that `low` kept every one of `medium`'s hits on this material at
2.2x less wall clock, not that the two are equivalent. The effective n is again
8 per type, so 0 of 8 new errors admits a true rate around 30 percent at 95
percent confidence. And the 0-of-16 repeat agreement follows arithmetically from
64/64 for the same reason as in the arm above; it is not separate evidence.
Separating the levels would take a harder frozen set - more distinct questions
rather than more repeats of these.

The `--reasoning-budget 8192` was left identical in both arms deliberately, as a
shared safety net rather than a second experimental variable. It was never
reached: 2995 tokens was the worst case at `low` and 3532 at `medium`.

#### Changing the effort level throws away the whole prompt cache

The level is prompt steering, not a decode constraint, and where it lands
matters. Asking the server to render the template (`/apply-template`) with a
short message, at each level:

| level | rendered length | system block |
|---|---:|---|
| no kwarg | 63 | none |
| `medium` | 63 | **none - identical to passing no level** |
| `low` | 229 | "Reasoning effort is set to low. Keep your thinking brief..." |
| `xhigh` | 300 | "...think carefully, validate key assumptions..." |

Two things fall out of that table. `medium` is the absence of an instruction,
not a middle setting, which is why the arm above is described the way it is.
And the instruction is prepended to the **system block**, so two levels differ
from the very first token of a 120K prompt.

Which means the prefix cache is worthless across a level change, and
`--cache-reuse 256` does not shift its way out of it. Measured on the same 120K
prompt, switching from `medium` to `low`:

| query | level | prefilled tokens | cached | prefill | generation |
|---|---|---:|---:|---:|---:|
| 1 | medium | 119963 | 0 | 390.1 s | 45.3 s / 1859 tok |
| 2 | low | 119993 | 0 | 392.2 s | 5.0 s / 225 tok |

A full 120K prefill costs about 390 s here, near 307 tok/s. Interleaving the two
levels request by request would have paid that on every one of 64 queries -
around 7 hours instead of the 18 minutes the blocked run took. So each level
runs as one block, paying prefill once; within a block every query reported
`cached` near 119000 and `cached == 0` never recurred. This is specific to the
effort level: `enable_thinking: false` leaves the prefix alone, which is why the
arm comparison above could alternate freely.

The same table is also why the latency column exists in the form it does.
Wall-clock per request was 436 s against 400 s - a 9 percent difference that
would have read as "the level changes nothing", while the generation underneath
differed 9x. Splitting `prompt_ms` from `predicted_ms` is not bookkeeping here;
without it the measurement says the opposite of what happened. Pilot:
`scripts/kv_pilot_effort.py`, `data/kv-effort-prompt-cache-pilot.json`.

Levels the template accepts are `low`, `medium` and `xhigh`. `high` is silently
remapped to `xhigh`; anything else raises. `xhigh` is the template's own default,
and whether a server ever serves it depends on the flag: `--reasoning-effort`
defaults to the literal `default`, which leaves the template's choice alone. Set
it to a level, as the profile here does, and that level is what the template
sees.

### Exhausting the reasoning budget closes the thought, it does not cut the answer

Every run above had `--reasoning-budget 8192` and none of them reached it - the
longest thought observed was 3532 tokens, 43 percent of the budget. So the
failure mode had never been seen. llama.cpp has a specific mechanism for it:
`--reasoning-budget-message` injects text *before* the end-of-thinking tag when
the budget runs out, which means the server closes the block itself rather than
stopping generation. Whether that yields a truncated answer or an early one is
the question.

One arm, budget 512, everything else identical to the medium arm above, same 16
questions and same seeds. `max_tokens` was set to 1024 so that a budget stop
could be told apart from a `max_tokens` stop; no request finished on `length`.

| run | type | correct | completion tokens, median | reasoning chars, median |
|---|---|---:|---:|---:|
| budget 8192, `medium` | retrieval | 8/8 | 178.5 | 447 |
| budget 8192, `medium` | counting | 8/8 | 2532 | 4401 |
| budget 512, `medium` | retrieval | 8/8 | 178.5 | 448 |
| budget 512, `medium` | counting | 8/8 | 515 | 1110 |

The budget binds only where the thought is long. Retrieval is untouched, to the
half-token: 178.5 either way. Counting is capped, and visibly so - 7 of the 8
counting queries stopped at exactly 515 tokens.

Nothing about the stop is ragged. All 16 requests returned `finish_reason:
stop`, no answer came back empty, and every answer was bare - a number, or a
single `WEZEL-xxx`. The reasoning text is what gets cut, mid-sentence, in the
middle of an enumeration: `- Akapit 232: partycja 40\n- Ak`. A following turn
works normally and reuses the prefix (`cached` 119959).

#### The written enumeration is not what fixes the arithmetic

Counting scored 8/8 on 4.9x fewer tokens while its enumeration was demonstrably
incomplete. In one query the cut lands at paragraph 119 of roughly 800, and the
count is still right. Whatever repairs the arithmetic that reasoning-off gets
wrong, it is not the completeness of the list the model writes out. That sits
alongside the earlier finding that a reasoning-off model
[names the entries correctly and still miscounts them](#counting-fails-while-enumeration-mostly-works).

We cannot say which mechanism this is. Eight correct counts out of eight is
consistent behaviour on these eight items, not proof that chance is excluded,
and it does not show whether the answer is read off attention over the context
with the enumeration as theatre, or something else. And the ceiling caveat applies with full force:
8 distinct questions per type, `medium` at budget 8192 already scored 8/8 on
them, so a tie discriminates nothing and 0/8 errors admits a true error rate
around 30 percent at 95 percent confidence. The supported claim is that on this
material the budget is not the binding constraint, and that in all 16 answers
here running out of it left the reply complete - not that 512 is enough, and not
that an answer can never be damaged. Data:
`data/kv-budget-512-120k.json`, `scripts/kv_run_budget.py`,
`scripts/srv-kv-budget.sh`.

#### Two levers, one soft and one hard

The two ways to spend fewer reasoning tokens are not variants of one knob. They
act in different places, and that decides how each one behaves:

| | `reasoning_effort` | `--reasoning-budget` |
|---|---|---|
| where it acts | a sentence the chat template puts in the prompt | a cap on how many tokens the thinking block may generate |
| what the model knows | it reads the instruction and may or may not follow it | nothing; the server ends the block from outside |
| effect on the thought | shorter and properly closed, when it is followed | truncated where the cap falls, mid-sentence |
| predictability | bimodal here: 6 of 32 counting queries ignored `low` and ran to ~2900 tokens | exact: 7 of 8 counting replies stopped at 515 tokens |
| effect on the prompt cache | changing the level invalidates the whole prefix | none, the prompt is untouched |
| how it is set | per request | a server flag, so each value needs its own server |

That is why the budget produced a clean 4.9x token reduction on counting while
`low` produced a 6x drop in the median and no change at the p90. The instruction
can be declined; the cap cannot.

What neither lever does is make the reply shorter. Retrieval answers came back
at a median of 179 completion tokens at `medium`, 181 at `low` and 178.5 under
the budget, because the tokens being cut are the ones the model spends thinking,
and retrieval barely spends any.

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
indistinguishable on these questions, because neither was reached. A budget low
enough to be reached is measured in [Exhausting the reasoning budget closes the
thought, it does not cut the
answer](#exhausting-the-reasoning-budget-closes-the-thought-it-does-not-cut-the-answer).

The full table is in
[power-and-undervolt.md](power-and-undervolt.md#energy-per-token-is-the-wrong-metric-when-the-setting-changes-the-token-count).

Note that `medium` here means what the server was started with, and that level
puts no instruction into the prompt at all; `low` and `xhigh` are the levels
that add one. See [Changing the effort level throws away the whole prompt
cache](#changing-the-effort-level-throws-away-the-whole-prompt-cache).

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
