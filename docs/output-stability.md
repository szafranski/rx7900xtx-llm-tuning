# Testing whether a GPU setting changed what the model says

The usual way to validate an undervolt or a power cap on an inference box is:
run it, see that it does not crash, check that tokens per second did not drop.
That test cannot see the failure mode people actually worry about, which is the
card computing a slightly wrong number and the model producing a slightly wrong
answer without any visible symptom.

This is the gate we used instead, what it found, and what it does not cover.

## What is compared

Every request in a run records a SHA-1 of the response text, truncated to
12 hex characters, and a second SHA-1 of the reasoning trace:

```python
"sha1": hashlib.sha1(content.encode()).hexdigest()[:12]
```

Two runs are then compared **position by position**: request 1 of session A
against request 1 of session B, request 2 against request 2, and so on.

## Why position by position, and not run against run

Our first version of this gate compared each request in a session against the
first request in the same session, and reported a fault when they differed. That
was wrong, and it produced a false alarm that cost us a phase of work.

`llama-server` carries state between requests. Request 3 does not start from the
same cache state as request 1, so it has no obligation to produce the same text.
Within a session the outputs are *expected* to differ. Comparing them measures
the cache, not the hardware.

The comparison that means something is the same position in two different
sessions. That is what the current gate does
(`scripts/soak-and-output-gate.sh`), and the sequence it compares against lives
in `data/reference-sequence-*.json`.

## What the data shows

**Twelve runs, three ASPM settings, throughput spread 6.5 percent, two distinct
outputs.** `data/aspm-under-load.jsonl`, all at 272 W / -75 mV / 2200 MHz.
Decode throughput ranges from 46.3 to 49.3 tok/s across the settings, and every
first request produced hash `bb0c0ed50595`, every second request produced
`c94f4b0b2760`. A setting that measurably moves speed left the generated text
untouched.

![Throughput moves, generated text does not](../charts/output-stability.svg)

**Four paired positions across two passes.** `data/spec-variants-paired.jsonl`,
at factory voltage. `p1` and `p2` are two passes over the same four
configurations; each position matches its counterpart in both the response hash
and the reasoning hash, while `r1` and `r2` within a pass differ from each other
as expected.

**The same output at two different voltages and power caps.** The
`mtp+ngram-map-k` request that produced `bb0c0ed50595` / reasoning
`3cddaf04c4b1` in `data/spec-vs-none.jsonl` (303 W, 0 mV offset, unrestricted
clock) produced the identical pair as the first request of the soak in
`data/soak-efficient-ngram-runs.jsonl` (272 W, -75 mV, 2200 MHz cap).

**Eleven positions through a 30-minute soak.** The soak session matched the
first 11 entries of the reference sequence. Perplexity over wikitext-2 was
5.9335 before and after, `dmesg` showed no new `amdgpu` entries, and junction
temperature peaked at 86 C.

## What this does not show

These limits are part of the result, not disclaimers appended to it.

- **It is not bit-exactness of the computation.** A hash over the response text
  proves the *decoded text* matched. It says nothing about logits, tensor
  contents, or intermediate arithmetic. Two different logit vectors can decode
  to the same token. Calling this "bit-exact inference" would be wrong.
- **The hash is truncated to 48 bits.** That is fine for detecting a
  regression and is not a cryptographic guarantee.
- **The automated gate compares the response text only.** It records the
  reasoning hash but does not fail on it. The reasoning hashes cited above were
  checked by hand.
- **The 11-position soak match was a prefix comparison.** The reference sequence
  holds 70 positions and the confirming session ran 11, so the gate compared
  `min(70, 11) = 11`. Positions 12 to 70 were not re-run under the efficient
  profile. The gate takes the shorter of the two sequences by design, which
  means a truncated session passes; that is a real weakness and anyone reusing
  the script should decide whether they want it.
- **One card, one sample.** Nothing here addresses silicon variation. It says
  this card at -75 mV produced the same text as this card at 0 mV, under the
  configurations listed, with this build.
- **Perplexity unchanged to four decimals bounds gross regression only.** It
  does not detect a small quality change.

## Reusing the gate

`scripts/soak-and-output-gate.sh` applies a GPU profile, verifies the driver
accepted it, runs a cold perplexity check against a fixed reference, soaks for a
chosen duration, and then compares the output-hash sequence against
`results/reference-sequence-<tag>.json`, creating the reference on the first
run. It aborts on a junction-temperature guard and on new `amdgpu` kernel
messages.

Two details are worth copying if you write your own:

- Stop the server *before* running the perplexity check. An earlier version ran
  it against a live server and the numbers were not comparable.
- Clear the abort marker in an `EXIT` trap, or one failed run poisons the next.
