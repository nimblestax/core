---
title: Nimblestax skills
description: The agent skills nsx init writes into your repo, why there are two copies, and how they stay in step with Nimblestax.
---

A Nimblestax skill guides a coding agent through one task with Nimblestax's commands, such as adding a source. `nsx init` writes them into your project, and you commit them like any other file.

```console
$ nsx init kettle
...
Wrote Nimblestax Skills for coding agents:
  .agents/skills/nimblestax-add-model
  .claude/skills/nimblestax-add-model
  .agents/skills/nimblestax-add-source
  .claude/skills/nimblestax-add-source
```

Each skill is one `SKILL.md` that names the commands to run. It doesn't list a kind's fields. It tells the agent to run `nsx schema <kind>`, so the fields come from the Nimblestax you have installed. No skill deploys: an agent writes the change, and a person promotes it.

## Where they go

Skills follow the [Agent Skills](https://agentskills.io) standard and use only its fields, so every agent that reads the standard gets the same steps.

`.agents/skills/` holds the main copy, in the folder many coding agents share. Claude Code reads only `.claude/skills/`, so it gets an identical copy. They are copies, not symlinks, because symlinks don't check out reliably on Windows.

Nimblestax only ever adds `nimblestax-*` folders. Your own skills, settings and other files in `.agents/` and `.claude/` stay as they are, and a `nimblestax-*` folder that already exists is left alone. If Git ignores either folder, `nsx init` warns with [`NSX914`](../reference/rules/nsx914.md), because skills that aren't committed stay on one machine.

To write no skills, run `nsx init --skills none`. `nsx skills update` writes them later if you change your mind.

## Keeping them in step

Each skill records the Nimblestax version that wrote it, in its front matter:

```yaml
metadata:
  nimblestax-version: "0.1.0"
  nimblestax-digest: "..."
```

After you upgrade Nimblestax, `nsx validate` warns with [`NSX129`](../reference/rules/nsx129.md) for each skill an older version wrote, because its steps can name commands that have changed. A warning doesn't fail validation.

`nsx skills update` rewrites both copies of each skill to the installed version:

```console
$ nsx skills update
Updated these Nimblestax Skills. Commit them:
  .agents/skills/nimblestax-add-source
  .claude/skills/nimblestax-add-source
```

`nimblestax-digest` records the text Nimblestax wrote, so `nsx skills update` can tell your edit from an older Nimblestax's text. If you edited a skill, it writes nothing, reports [`NSX915`](../reference/rules/nsx915.md) and shows the difference. Move your steps into a skill of your own, outside the `nimblestax-*` folders, or run `nsx skills update --force` to replace them.

## Next steps

- [`nsx skills update`](../reference/commands/skills.md#update) lists its options and its JSON result.
- [`nsx init`](../reference/commands/init.md) lists `--skills` with its other options.
