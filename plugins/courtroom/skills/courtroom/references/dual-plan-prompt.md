# Dual-Plan Prompt Template

This prompt is sent to Codex CLI during Phase 2.5 (--dual-plan mode only). Codex generates
its own independent implementation plan before seeing Claude's plan. Replace all
`{{PLACEHOLDER}}` values before invocation.

---

## Prompt

You are a **Senior Engineer** tasked with implementing a feature or fix. You have been given
a task description and access to the relevant source files. Your job is to produce YOUR OWN
independent implementation plan — not to review or critique anyone else's approach.

Think from first principles. Do not try to guess what another engineer might propose.
Produce the plan you would actually implement if this were your task.

## Project Context

- **Project type**: {{PROJECT_TYPE}}
- **Language/Framework**: {{LANGUAGE_FRAMEWORK}}
- **Conventions**: {{PROJECT_CONVENTIONS}}

## The Task

{{TASK_DESCRIPTION}}

## Files to Consider

The following files are relevant to this task (paths relative to your working directory):

{{AFFECTED_FILES}}

Read the files to understand the existing code before proposing your plan. In repository
mode your working directory is the repository itself and you may read further files in it
read-only; in copy mode only the files listed above are available.

---

## Your Plan

Produce a concise implementation plan (under 500 words) covering:

1. **Approach** — What is your strategy? What is the core mechanism you would use?
2. **Files to Modify** — Which files, and what specifically would change in each?
3. **Key Decisions** — What are the 2-3 most important design decisions? What alternative did
   you consider and why did you choose this approach?
4. **Edge Cases** — What are the top 2-3 failure modes or edge cases you would address?
5. **Risks** — What is the biggest risk in your approach?

## Critical Rules

1. This is YOUR plan. Do not copy or mirror what another engineer might propose.
2. Be specific about mechanisms — vague plans are not useful.
3. Keep it concise. Quality over length.
4. If the task is unclear, state your assumptions explicitly.
5. Do NOT produce OBJECTION: blocks or cross-examine anything — this is a planning step, not
   a review step.
