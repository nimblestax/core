---
name: nimblestax-add-model
description: Add a Gold Model to a Nimblestax project, from its SQL and YAML files, with its Tests, to a passing `nstx validate`. Use when asked to add a gold table, a fact or a dimension.
metadata:
  nimblestax-version: "NIMBLESTAX_VERSION"
  nimblestax-digest: "NIMBLESTAX_DIGEST"
---

# Add a Gold Model

1. Run `nstx schema model` for the fields the installed Nimblestax accepts. Take field names and values from its output, not from memory.
2. Write `domains/<domain>/models/<layer>/<name>.sql` as one query, and `<name>.yaml` beside it with `kind: model` and the `version` the schema names.
3. Read tables by their Logical Names, such as `sales.silver.orders`, never by a real table name.
4. If the project's other models name an `owner`, set it to the team that answers for this table. If you don't know which team, ask; don't invent one. Otherwise leave `owner` out.
5. Add `tests` for what must hold of the whole table: at least `unique` on the columns that identify a row, and `references` for each column that points at another table's key.
6. Run `nstx validate --json`. For each diagnostic, apply its `fix`, then run it again until it reports none.
7. Run `nstx compile --env dev` and read the SQL Nimblestax generates for the model.
8. If you have a Preview Environment, run `nstx preview`, then `nstx test --json`, and fix what fails.

Stop there. Changes reach an Environment through a pull request, and a person promotes them.
