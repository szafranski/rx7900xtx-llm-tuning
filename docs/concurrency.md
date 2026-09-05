# More than one request at a time

Everything else in this repository measures one request against an idle card.
That is the wrong shape for agent work, where a coding assistant opens a main
thread and two smaller workers against the same server. This file is what
happened when we did that.

## Read this first

These runs are held to a lower standard than the rest of the repository, and
the difference matters for what you can take from them:

- One run per configuration. No repetitions, no null pair.
- The server was the live production instance, not a clean bench server.
- The desktop was active, so `vram_mib` carries whatever the compositor and the
  browser were holding at the time.
- No GPU telemetry. No board power, no junction temperature, no fan.
- The prompts are not committed. They were local source files from this host
  with paths inside them. Their sizes were 8390, 55 and 2121 tokens.

Per `methodology.md`, single-run comparisons here rank options and do not size
the gap between them. Everything below is written to that limit. Numbers come
from `data/concurrency-20260905.jsonl` (13 requests, server-reported `timings`)
and `data/concurrency-20260905-monitor.jsonl` (1446 samples at 1 Hz).

The server ran the configuration in the main README plus `--ctx-size 147456`,
`--parallel N`, `--kv-unified`, `--cache-prompt`, `--cache-reuse 256`,
`--metrics`, `--no-context-shift` and `--timeout 900`.

## `--kv-unified` gives every slot the full window

With the flag, the KV cache is one shared pool and every slot reports the whole
window. The startup line says so directly, and says the same thing at two slots
and at three:

```
srv load_model: initializing, n_slots = 2, n_ctx_slot = 147456, kv_unified = 'true'
srv load_model: initializing, n_slots = 3, n_ctx_slot = 147456, kv_unified = 'true'
```

This is the behaviour of the flag, read out of the server's own log, not a
measurement subject to run-to-run noise. We did not run the same test without
the flag, so nothing here says what slots cost in the other mode. That is the
point of writing the flag down: any figure for slot count carries an assumption
about which mode was in effect, and ours is stated.

## A prompt cache hit removes nearly all of the prefill

The same 8390-token prompt, sent twice:

| pass | `cache_n` | new tokens | prompt phase |
|---|---:|---:|---:|
| cold | 0 | 8390 | 15.9 s |
| repeat | 8386 | 4 | 0.22 s |

Four tokens were recomputed, not one. The 2121-token prompt behaves the same
way, 2117 cached and 4 recomputed, so the remainder looks like a fixed tail
rather than anything that scales with the prompt. We did not chase down which
four tokens they are.

These come from the server's own `timings` block, so desktop VRAM drift does not
touch them. In this run, reusing the stable prefix avoided nearly all of the
prefill. A prefix that changes between turns cannot be reused, but we did not
measure what breaks it.

## The queue is invisible to the client

Three requests at two slots. The third waits, and nothing tells the client that:

| request | prompt | decode | wall |
|---|---:|---:|---:|
| main | 8390 | 30.6 tok/s | 42.3 s |
| worker-m | 2121 | 31.4 tok/s | 27.1 s |
| worker-s | 55 | 36.8 tok/s | 38.9 s |

The smallest request took the second longest. `llamacpp:requests_deferred` sat
at 1 from 12:07:57 to 12:08:12 in the monitor samples, and
`n_busy_slots_per_decode` reached 1.99, so both slots were genuinely full. From
the client side this is not an overload signal, it is one request that happened
to be slow.

For this workload, limiting client concurrency to the slot count is what avoided
deferred requests. `llamacpp:requests_deferred` is the only field here that
separates queueing from slowness, so it is the one to watch.

One operational note from the same log. Of 1446 polls, 21 got no answer from
`/metrics` within a 2-second timeout, and they cluster during heavy prompt
processing. Monitoring drops out exactly when it is most wanted. Two seconds is
too short; we did not measure what is enough.

## In this run, a third slot did not shorten time to the last response

Same three requests, `--parallel 3`:

| | 2 slots | 3 slots |
|---|---:|---:|
| last response | 42.3 s | 41.5 s |
| smallest request, wall | 38.9 s | 30.1 s |
| smallest request, decode | 36.8 tok/s | 23.0 tok/s |
| `requests_deferred`, max | 1 | 0 |

One run each, so read this as a ranking and not as a measured gap: the extra
slot showed no visible gain in time to the last response.

Three requests against three slots did clear the queue, `requests_deferred`
stayed at 0 throughout. It came back as soon as there was one request more than
slots: at four requests against three slots it sat at 1 for about 14 seconds,
the same shape as three requests against two slots. The threshold moved by one
request rather than going away.

What else changed is the small request. It stopped waiting and finished 8.8 s
sooner, while its own decode rate was lower, 23.0 against 36.8 tok/s.

We are not reporting a VRAM cost for the third slot. Idle readings differ by
about 300 MiB between the two windows, 24063 MiB against 24429 MiB. That is not
attributable to the slot: the desktop was active throughout, the idle reading
drifts by 93 MiB inside the two-slot window on its own, and a later two-slot
reading taken outside these windows, so not in the committed data, was 310 MiB
below the one here. The drift and the difference are the same size. This test
cannot separate them.

## What we did not measure

- Any repetition, so nothing here sizes a gap.
- Board power or temperature under concurrent load.
- Behaviour at prompts near the full 147K window, where prefill dominates.
- Whether the throughput ranking survives on a quiet desktop.
