# Approximate Decontamination Pilot

When freezing a `pretrain` release, Derlem reports approximate document
similarity against eval and holdout sources. The report runs after the exact
decontamination gate and is bound to the frozen release snapshot under
`gate_results.approximate_decontamination`.

## Policy

- Exact document matches remain a hard gate and block the release.
- The approximate pilot is report-only and cannot block freeze by itself.
- Potential matches are human-review candidates, not automatic leak decisions.
- The result is `not_applicable` when no eval/holdout source exists.
- Candidate overflow is never treated as clean; it returns `inconclusive`.
- Raw release and evaluation text is not persisted in the report or temporary index.

## Method

Method identifier:
`normalized-word-3gram-simhash64-v1-hamming10-bands8x8-v1`.

1. Plain text/JSONL content is selected; canonical conversation/preference records
   use messages, tools, and exportable semantic text instead of the JSON envelope.
2. Selected text passes through Derlem's canonical document normalization.
3. Word 3-grams are extracted from documents containing at least five tokens.
4. A deterministic BLAKE2b-based 64-bit SimHash signature is produced.
5. Eval/holdout signatures are split into eight 8-bit bands in a temporary SQLite index.
6. At most 5,000 references sharing one or more bands are compared per pretrain document.
7. The best candidate with Hamming distance at most 10 is reported as a potential match.

The temporary index stores only the 64-bit signature, source SHA256, and line
ordinal, and is deleted when the job ends. Up to 20 sample matches include
source identities, ordinals, Hamming distance, and an estimated similarity
ratio; they never include text.

## Outcomes

- `reported` with `potential_match_count = 0`: no match was found in the scanned candidate space.
- `reported` with a positive count: candidates require human review.
- `inconclusive`: at least one document exceeded the 5,000-candidate bound; the result is not clean.
- `not_applicable`: the release is not pretrain or no eval/holdout reference exists.

The Jobs view reports live reference/release document counts, potential matches,
and candidate overflows.

## Known Limits

SimHash with banded candidate selection is approximate and can produce false
positives and false negatives. Short documents are not indexed. Heavily
reordered, translated, or transformed leaks may escape detection. The pilot is
therefore neither a legal conclusion nor a final quality decision. Threshold
and band settings must be calibrated on real Derlem corpora before this can
become a hard gate.
The calibration workflow is defined in the
[SimHash Calibration Report](similarity_calibration.en.md).
