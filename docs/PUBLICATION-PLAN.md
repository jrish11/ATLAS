# Proposed GitHub structure and publication gate

The owner approved PUBLIC publication. GitHub identity jrish11 (ID123313048) was verified through the connected account; new public repository https://github.com/jrish11/ATLAS was created after checking name availability. No unrelated repository was altered. A public upstream network fork cannot be private; a private derived repository is distinct and should retain an upstream remote and attribution.

Prepared layout outside this root:

- `repository/`: latest sanitized Mac source with current README/CHANGELOG/RELEASES/metadata/build/migration/test/update docs.
- `source-archives/`: six verified historical sanitized source snapshots, v3 throughv3.5, with hashes and original commit/date mapping.
- `experiments/`: separate Windows source-only and remote experimental snapshots with their exact commits/status; no ready PWA is asserted.
- `release-assets/`: only the separately verified public-safe v3.5 Mac ZIP; no private companion or earlier private ZIP.
- `history/`: complete clean upstream bundle. Original customized history remains untouched in its local repository.
- `audit/`: export mapping and audit evidence; review before selecting any file for publication.

The full local object audit covered2502 objects/~227MB.122 local development commits contain non-noreply author email metadata; personal project references occurred in historical blobs. Those local commits are not automatically publication-safe. The original history was NOT rewritten. Snapshots replace personal project references in historical notes/synthetic tests with generic examples; mapping records changed filenames. No production runtime source required personal-data replacement. Original MIT notices remain byte-identical.

A publication option is to retain clean upstream ancestry and add clearly identified sanitized snapshot commits/tags for each verified version, while preserving original hashes in a provenance manifest. This is a new derived history, not the original full customized commit graph. This is the chosen publication arrangement. Sanitized source commits/tags retain original hashes and dates in provenance; the original customized history remains local and unchanged. Do not silently publish the raw graph or invent missing older versions. Upstream workflows/funding metadata are retained under `docs/upstream-workflows`, outside active GitHub workflow locations, pending explicit review. Rebuild/revalidate the final sanitized commit before calling it a reproducible source release.
