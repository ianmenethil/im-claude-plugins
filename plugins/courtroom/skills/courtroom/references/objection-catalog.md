# Weak Objection Catalog

Known objection patterns that are consistently low-value or false positives. When a Codex objection matches a pattern below and no concrete technical failure mode remains beyond that pattern, classify it as FILTERED and exclude it from the rebuttal phase.

---

## Category 1: Style and Preference Objections

### WO-STYLE-01: Naming preferences
Codex suggests renaming variables, functions, or files to its preferred convention when the existing names are clear and consistent with the project.

### WO-STYLE-02: Import ordering
Codex suggests reorganizing imports or switching between named and default imports when both are functionally equivalent.

### WO-STYLE-03: Syntax alternatives
Codex suggests ternary vs if/else, arrow vs function declarations, forEach vs for-of, or other syntactically equivalent alternatives.

### WO-STYLE-04: Comment additions
Codex suggests adding JSDoc, inline comments, or documentation when the code is self-documenting.

---

## Category 2: Over-Engineering Objections (YAGNI)

### WO-YAGNI-01: Premature abstraction
Codex suggests creating interfaces, abstract classes, or factory patterns for a single concrete implementation.

### WO-YAGNI-02: Configurability for hardcoded values
Codex suggests making constants configurable (env vars, config files) when they are used once and unlikely to change.

### WO-YAGNI-03: Unnecessary caching layer
Codex suggests adding caching for operations that are not performance-critical or are called infrequently.

### WO-YAGNI-04: Future-proofing
Codex raises concerns about "what if we need to scale this later" or "what if requirements change" for a clearly scoped task.

### WO-YAGNI-05: Dependency suggestions
Codex suggests adding a third-party library for something achievable in 1-5 lines of native code.

---

## Category 3: Redundant Validation Objections

### WO-VAL-01: Re-validation of already-validated input
Codex suggests runtime validation for input that is already type-checked or pre-validated before it reaches this code — parameters covered by TypeScript's strict mode, or internal helper functions that only receive validated input from their callers.

### WO-VAL-03: Framework-guaranteed values
Codex suggests null-checking values that are guaranteed non-null by the framework (e.g., React context with a provider, Express req.params with a route param).

---

## Category 4: Scope Creep Objections

### WO-SCOPE-01: Tangential refactoring
Codex suggests refactoring existing code that is not directly affected by the planned changes.

### WO-SCOPE-02: Unrelated feature additions
Codex suggests adding features or capabilities beyond the stated task scope.

### WO-SCOPE-03: Comprehensive test suite
Codex suggests writing tests for pre-existing code that the plan does not modify, beyond testing the new changes themselves.

### WO-SCOPE-04: Documentation overhaul
Codex suggests updating README, API docs, or architecture docs for changes that are internal implementation details.

---

## Category 5: Framework-Idiomatic Pattern Challenges

### WO-FW-01: Next.js / Remix conventions
Codex challenges file-based routing, server components, loader patterns, or other framework conventions as "unusual" architecture.

### WO-FW-02: React patterns
Codex challenges custom hooks, context providers, render props, or component composition patterns that are idiomatic React.

### WO-FW-03: Express/Fastify middleware
Codex challenges middleware chaining, error-handler signatures (4 params), or route-level middleware as "unnecessary indirection."

### WO-FW-04: ORM patterns
Codex challenges Prisma's generated types, Drizzle's query builder syntax, or TypeORM's decorator patterns as "non-standard."

---

## Category 6: Trivially Wrong Objections

### WO-WRONG-01: Phantom file references
Codex objects about a file or function that does not exist in the codebase (hallucinated reference).

### WO-WRONG-02: Outdated API knowledge
Codex claims an API or library function does not exist or works differently, when it does exist in the version used by the project.

### WO-WRONG-03: Platform confusion
Codex raises concerns about browser APIs when the code runs on Node.js, or vice versa.

---

## How to Use This Catalog

After Codex returns objections in Phase 3:

1. For each objection, check if it matches any pattern above.
2. If it matches **and no concrete technical failure mode remains** beyond the pattern, classify as `FILTERED` with the catalog ID (e.g., `FILTERED: WO-YAGNI-01`).
3. Filtered objections are excluded from the rebuttal phase.
4. Include the filter count in the final report: "X objections auto-filtered (Y style, Z YAGNI, ...)".
5. If an objection partially matches but has a genuine technical core, do NOT filter it — let it through to rebuttal.
