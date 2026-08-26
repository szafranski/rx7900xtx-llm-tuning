# Settings that did not work

Each of these was tried and measured. Negative results with numbers attached
save the next person the run.

| setting | effect | data |
|---|---|---|
| `GGML_VK_DISABLE_MMVQ` | -9.1% decode with MTP enabled | `data/spec-vs-none.jsonl` |
| `--ubatch-size 288` as the default | no decode gain, about -27% prefill | `data/context-128k.jsonl` |
| `--spec-draft-n-max` 4, 5 or 6 | slower at every value, more VRAM | `data/spec-vs-none.jsonl` |
| `--spec-type ngram-cache` | about -44% throughput | `data/spec-vs-none.jsonl` |
| `--parallel 3` for a single stream | about -1% throughput, +1098 MiB VRAM | `data/context-128k.jsonl` |
| BF16 vision projector | +288 MiB, no improvement | `data/vision.jsonl` |
| ASPM `performance` | +1% under load, +1.5 W constant at idle | `data/aspm-idle.jsonl` |
| voltage offset -150 mV | silently clamped, no crash, not applied | `data/soak-efficient-ngram-runs.jsonl` |

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
