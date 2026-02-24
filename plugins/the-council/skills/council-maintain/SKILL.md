---
name: council-maintain
description: Compact council memory — deduplicate and prune using the curator agent.
---

# Council Memory Maintenance

## Step 1: Check memory health
Call `council_memory_status` with `project_dir` set to the current project root directory (absolute path).

If no compaction is recommended, report that memory is healthy and stop.

## Step 2: Run curator
Use the **Task tool** to launch the `curator` subagent (subagent_type: "the-council:curator") with this prompt:

> Compact the council memory in `{project_dir}`.
> For each role (strategist, critic, hub): call council_memory_load to see current entries,
> read the role's log file, identify duplicates/superseded/mergeable entries,
> then call council_memory_compact with the compacted entries JSON array.
> Report what you changed.

The curator runs in its own context window — zero cost to this session.

## Step 3: Report
Show the user what was compacted and the before/after entry counts.
