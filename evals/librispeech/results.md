# LibriSpeech accuracy results

Fixtures: chapter-level concatenations of LibriSpeech test-clean / test-other
utterances (~8 min each; cap 480s), references joined from the `*.trans.txt`
ground truth — exact, so absolute WER is trustworthy. `hf-dummy` is the
Hugging Face `hf-internal-testing/librispeech_asr_dummy` validation split
concatenated into one ~8-min fixture (clean speech, smoke test).
Chapters picked deterministically (evenly spaced over the sorted list).
WER/CER are micro-averages (total edits / total reference words) across the
row's fixtures. Decoding is deterministic (greedy or fixed beam), so deltas
are real. Hardware: Apple Silicon, Python 3.9.6. Lower is better.

| label | source | fixtures | audio_s | wall_s | WER% | CER% | ref words | flags |
|-------|--------|---------:|--------:|-------:|-----:|-----:|----------:|-------|
