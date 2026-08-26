# Prompts

The fixed inputs the benchmarks replay, so that every configuration is measured
on identical work.

| file | size | used by |
|---|---:|---|
| `P20K.txt` | ~19,000 tokens | the soak and most throughput runs |
| `P50K.txt` | ~48,600 tokens | the keyed-retrieval quality runs |
| `P98K.txt` | ~92,400 tokens | the 128K context and needle runs |
| `Q16.txt` | ~48,600 tokens | quality runs, alternate corpus |
| `turns.json` | 10 turns | the multi-turn session benchmark |
| `multiturn-transcript.json` | | recorded transcript of that session |
| `manifest.txt` | | token counts as measured by this model's tokenizer |

## Provenance and licence of the corpora

`P20K.txt`, `P50K.txt`, `P98K.txt` and `Q16.txt` are concatenations of C++
source files from `llama.cpp` (`llama-adapter.cpp`, `llama-arch.cpp`,
`llama-batch.cpp`, `llama-chat.cpp`, `llama-context.cpp`), each preceded by a
`// ==== FILE: name ====` header and truncated to the target length.

That source is **MIT licensed, Copyright (c) 2023-2024 The ggml authors**, and
it is redistributed here under those terms. It is not covered by the CC BY 4.0
licence that applies to `../data/`, and the MIT notice above travels with it.

Into each corpus we inserted one short block of our own:

```
// ===== KLUCZ KONTROLNY =====
// Kod dostepu do wezla obliczeniowego: ZIELONY-KOT-7431
// Osoba odpowiedzialna: Jan Kowalski, szafa 07, serwerownia X
// ===========================
```

It is the needle for the retrieval checks: a string that cannot be guessed from
context, placed away from both ends of the prompt. The name and location are
placeholders. `turns.json` replays this project's own harness scripts as the
session content.

The Polish corpus `corpus/pl-mixed.raw` referenced in `manifest.txt` and the
`wikitext-2` test split used for perplexity are not redistributed here.
