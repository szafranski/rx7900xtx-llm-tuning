# Power cap, undervolt and clock limit

Nothing here overclocks. The power cap only ever moves downward from the
factory 303 W, memory clock is untouched, and the voltage offset is negative.

## Settings and what they cost

Relative to stock (303 W, 0 mV, unrestricted clock), running at 272 W:

| | change |
|---|---:|
| board power | -10% |
| throughput | -2.2% |
| energy per token | -7.9% |
| junction temperature | -8 C |

Adding the 2200 MHz clock cap on top brings the profile to roughly 11.9 percent
less energy per token, for about 5 percent less speed than the
maximum-performance variant.

272 W is the floor the vBIOS accepts on this card, not a value we picked.

![Energy per generated token](../charts/soak-energy.svg)

## Where the efficiency comes from

The card sits at its power limit continuously under decode load, so the limit,
not the clock target, decides the operating point. Lowering it moves the whole
voltage-frequency curve down. The clock cap then removes the top of the curve
where the last few percent of speed costs disproportionate power: the knee sat
near 2000 MHz at stock voltage and moved to about 2200 MHz once the undervolt
was applied, which is why 2200 is the value in the profile.

## The undervolt limit is not where the driver says it is

`-150 mV` was rejected in practice without any crash or error: the card kept
running and produced plausible output. That is the whole reason this repository
has an output-comparison gate rather than a stability test.

Below about -75 mV, with a clock cap active, the offset is silently clamped.
`pp_od_clk_voltage` reports the value you requested. The only sysfs channel that
reveals the clamp is `in0_input`. `scripts/amdgpu-profile.sh` reads the applied
value back and fails rather than trusting the write.

## Stability

30-minute soak at 272 W / -75 mV / 2200 MHz
(`data/soak-efficient-ngram-runs.jsonl`):

| | |
|---|---|
| perplexity before / after | 5.9335 / 5.9335 |
| new `amdgpu` kernel messages | 0 |
| junction max | 86 C |
| board power mean / max | 213.2 W / 261.0 W |
| output sequence | matched the reference, 11 positions |
| throughput difference vs 0 mV | 0.08% |

The output-sequence result is the one that took work to get right, and its
limits are set out in [output-stability.md](output-stability.md).

## ASPM

`performance` bought about 1 percent of throughput under load and cost about
1.5 W continuously at idle, plus 3.2-3.9 W on the CPU package at idle. Under
load the CPU package difference was below measurement noise, so the energy
saving from leaving ASPM at `default` survives.

For a machine that is idle most of the day, `default` wins. Data:
`data/aspm-under-load.jsonl`, `data/aspm-idle.jsonl`,
`data/aspm-cpu-package.jsonl`.

## Energy per token is the wrong metric when the setting changes the token count

This bit us and it is easy to repeat.

Reasoning effort `medium` shows the best joules per token of any reasoning
setting, and costs 1.2x to 4.8x more energy to answer the same question, because
it emits far more tokens. The per-token metric was improving while the thing we
actually cared about got worse.

Energy per token is only meaningful between settings that generate the same
number of tokens. That condition holds for the power, clock and ASPM
comparisons in this repository, where the output text is identical. It does not
hold for reasoning effort, context length, or anything else that changes what
gets generated. For those, measure energy per completed task.

## Reference: idle power

`data/idle-power.jsonl`, `data/idle-with-projector.jsonl`,
`data/display-refresh-idle.jsonl`. Idle board power sits near 16-17 W. Driving
the display at 144 Hz rather than 120 Hz cost about 4.3 W across the GPU and
CPU rails in one experiment; we did not establish a sharp threshold between the
two and left the monitor at 143.86 Hz.
