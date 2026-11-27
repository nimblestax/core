---
name: nimblestax-add-source
description: Add a Source to a Nimblestax project, from its YAML file to a passing `nsx validate`. Use when asked to add, declare or ingest a new source of landed files.
metadata:
  nimblestax-version: "NIMBLESTAX_VERSION"
  nimblestax-digest: "NIMBLESTAX_DIGEST"
---

# Add a Source

1. Run `nsx schema source` for the fields the installed Nimblestax accepts. Take field names and values from its output, not from memory.
2. Write `domains/<domain>/sources/<name>.yaml` with `kind: source` and the `version` the schema names. `<domain>` must be listed under `domains` in `nimblestax.platform.yaml`.
3. Run `nsx validate --json`. For each diagnostic, apply its `fix`, then run it again until it reports none.
4. Run `nsx compile --env dev` and read the SQL Nimblestax generates for the Source.

Stop there. Changes reach an Environment through a pull request, and a person promotes them.
