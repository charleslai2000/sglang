# scratch archive

Verbatim copy of every `.py` / `.sh` / `.patch` / `.diff` file that was under
`/tmp/opencode/**` and was **neither** byte-present in `HEAD` **nor** present in
the frozen `/opt` deploy trees, at the time of the source-authority correction.

Purpose: make `/tmp` disposable without losing anything. These are one-off probe
scripts, intermediate tree copies, generated diffs and superseded attempt copies
— they are archived for completeness, **not** endorsed as reusable tooling.
Reusable harnesses live in `3090-dev/harness/`; reusable gates/oracles/tools in
`3090-dev/gates/`, `3090-dev/tools/`, `3090-dev/deploy/`.

Index with sha256 and sizes: `../manifests/tmp-residual-disposition.json`.
