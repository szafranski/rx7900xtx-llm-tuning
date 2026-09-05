# Settings that did not work

Each of these was tried and measured.

| setting | effect | data |
|---|---|---|
| `GGML_VK_DISABLE_MMVQ` | -9.1% decode with MTP enabled | `data/spec-vs-none.jsonl` |
| `--ubatch-size 288` as the default | no decode gain, and 47.3 vs 53.0 tok/s on a 92K prompt with an image | `data/context-128k-cache-types.jsonl`, `data/context-32k.jsonl` |
| `--spec-draft-n-max` 4, 5 or 6 | slower at every value, more VRAM | `data/spec-vs-none.jsonl` |
| `--spec-type ngram-cache` | about -44% throughput | `data/spec-vs-none.jsonl` |
| max SCLK 1800 MHz | no J/token gain over 2000 MHz, 5% slower | `data/clock-cap-sweep.jsonl` |
| BF16 vision projector | +328 MiB, not faster | `data/projector-q8-vs-bf16.jsonl` |
| ASPM `performance` | +1% under load, +3.9 W on the CPU package at idle | `data/aspm-cpu-package.jsonl` |
| voltage offset past -100 mV | silently clamped under a clock cap, no crash | `data/undervolt-sweep-capped.jsonl`, `data/undervolt-clamp-vddgfx.tsv` |

A `--parallel 3` entry used to sit in that table. It was removed, not rewritten:
the dataset it cited holds no slot-count test, and no script here ever set
`--parallel` above 1, so its figures had no source. Slot count is measured, at a
different context length and with `--kv-unified`, in
[concurrency.md](concurrency.md).

## `GGML_VK_DISABLE_MMVQ` responds to presence, not value

This one is a trap rather than a tuning result, and we have not found it
documented anywhere.

The variable is read with `getenv`, and the code branches on whether the call
returned a pointer. Setting it to `0` therefore disables MMVQ exactly as
setting it to `1` does. The intuitive way to turn the option off is to set it to
zero, and that turns it on.

On this setup that cost 9.1 percent of decode throughput with MTP enabled. The
correct way to disable it is to not set the variable at all, i.e. `unset
GGML_VK_DISABLE_MMVQ`.

If you have this in a service file or a wrapper script with `=0`, it is active.
