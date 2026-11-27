---
title: nsx databricks
description: Run the Databricks CLI Nimblestax runs, with your arguments passed through.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx databricks <arguments>
```

It runs the Databricks CLI Nimblestax runs, the version `nsx --version` names, with every argument passed through as you wrote it. It prints what the Databricks CLI prints and exits with its exit code, so it has no `--json`. `nsx databricks --help` prints the Databricks CLI's help.

If Nimblestax can't find or download its Databricks CLI, it reports a diagnostic and exits 2.
