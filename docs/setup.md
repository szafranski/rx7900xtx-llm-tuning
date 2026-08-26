# Hardware, software and build

Every number in this repository came from this one machine. Version pins matter
here more than usual: the KV cache types and one of the speculation modes are
not available in upstream `llama.cpp`.

## Machine

| | |
|---|---|
| GPU | AMD Radeon RX 7900 XTX 24 GB (Navi 31, gfx1100), vBIOS `113-3E4710U-O4O` |
| CPU | AMD Ryzen 5 5600, 6 cores |
| RAM | 32 GB |
| OS | Bazzite 44.20260820.0 (Kinoite), kernel 7.2.0-ogc4.1.fc44.x86_64 |
| Driver | Mesa 26.2.1, RADV, Vulkan API 1.4.354 |

## Inference build

```
repo:    https://github.com/TheTom/llama-cpp-turboquant   (fork)
commit:  f91b7059427ea4901e2271763d308de1dd111373  (2026-08-22)
version: b10540   (self-reported by --version)
cmake:   -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
compiler: GCC 16.1.1
```

The build directory in the scripts is named `...-b10539-reasoning` because it
was created one commit earlier and reused. The binary that produced every number
here reports `b10540 (f91b70594)`; the commit hash above is the authority.

### Which results depend on the fork

This distinction decides whether a given result transfers to your setup.

| Feature | Upstream `llama.cpp` | Fork only |
|---|---|---|
| `--spec-type draft-mtp` | yes | |
| `--spec-type ngram-map-k`, `ngram-mod` | | yes |
| `--cache-type-v turbo4` | | yes |
| `--reasoning-effort` passed to the template | | yes, at this commit |
| Power cap, undervolt, clock cap, ASPM results | not applicable, these are driver-level | |

Anything measured with `turbo4` or `ngram-map-k` cannot be reproduced on
upstream `llama.cpp`. The GPU power and stability results do not involve the
fork at all and should transfer to any inference workload on this card.

## Model

```
Qwen3.8-27B-UD-Q4_K_XL.gguf   17,559,178,144 bytes   (unsloth)
mmproj-Q8_0.gguf                 629,247,008 bytes
mmproj-BF16.gguf                 931,146,432 bytes
```

Dense, not mixture-of-experts. That matters for the speculative-decoding result:
every generated token reads all 17.5 GB of weights.

## GPU profile

Applied at boot by a systemd unit running `scripts/amdgpu-profile.sh`, which
validates each value against the range the driver reports in
`pp_od_clk_voltage` and `power1_cap_min/max` and rolls back on any rejection.

```
power cap:        272 W        (factory 303 W, never exceeded)
voltage offset:   -75 mV
max SCLK:         2200 MHz
ASPM:             default
```

`amdgpu-profile.sh reset` returns the card to factory settings.

Two notes on the undervolt. Offsets below -75 mV are silently clamped once a
clock cap is in effect: the driver reports the value you asked for while
`in0_input` shows it did not take. And `-150 mV` failed without crashing,
which is why the output gate exists rather than a crash test.

## Not included here

- `wikitext-2-raw/wiki.test.raw`, used for every perplexity check. Fetch it
  yourself; only our per-chunk results are committed, in
  `data/perplexity-chunks.txt`.
- The model weights.
