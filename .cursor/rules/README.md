# Cursor Rule Files

This package contains two reusable Cursor `.mdc` rule files intended for general coding-agent behavior. They deliberately avoid project-specific details.

## Files

### `karpathy-behavioral-guidelines.mdc`
Use this as a strict behavioral guardrail for coding agents. It focuses on:

- Thinking before coding
- Simplicity
- Surgical changes
- Architecture preservation
- Goal-driven execution
- Honest verification
- Dependency discipline
- Security and data safety

### `agent-operating-rules.mdc`
Use this as a broader operating contract for agents working in real repositories. It focuses on:

- Understanding the existing system before editing
- Respecting user intent
- Producing clean diffs
- Not inventing context
- Production-grade minimalism
- Frontend/backend/data/documentation rules
- Commit-ready reporting
- Escalation rules

## Suggested location

Place both files in:

```text
.cursor/rules/
```

Suggested final structure:

```text
.cursor/
  rules/
    karpathy-behavioral-guidelines.mdc
    agent-operating-rules.mdc
```

Both files use:

```yaml
alwaysApply: true
```

You can change this to `false` if you want to invoke them only for selected tasks.
