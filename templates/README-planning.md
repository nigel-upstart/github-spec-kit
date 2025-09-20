# Planning with Claude Code

Spec-Kit now uses Claude Code's native plan mode for implementation planning instead of custom `/plan` commands. This provides better integration, safety, and user control.

## Quick Start

### Option 1: Provide Your Technology Choices

When you know what technologies you want to use:

```
claude: Please plan implementation for specs/001-user-auth/spec.md using:
- Python 3.11 with FastAPI
- PostgreSQL for storage
- pytest for testing
- Target: Linux server, 1000 req/s
- Constraints: <200ms p95 latency
```

### Option 2: Let Claude Suggest Technologies

When you want Claude to recommend the tech stack:

```
claude: Please plan implementation for specs/001-user-auth/spec.md

Generate a development specification with your recommended technology choices and wait for my approval before proceeding with the full plan.
```

## How It Works

1. **Claude enters plan mode** automatically when analyzing specifications
2. **Development specification**: Claude presents technology recommendations
3. **Your approval**: Review and modify the tech choices before planning
4. **Complete planning**: Claude generates all artifacts following spec-kit methodology
5. **Final approval**: Review the complete implementation plan before execution

## What Gets Generated

Claude will create these artifacts in your feature directory:

- **research.md** - Research findings for any unclear aspects
- **data-model.md** - Entity definitions and relationships
- **contracts/** - API contracts and specifications
- **quickstart.md** - Step-by-step validation procedures
- **plan.md** - Complete implementation plan with constitution checks

## Example Workflow

```bash
# 1. Create your spec (existing workflow)
claude: /specify Create user authentication system

# 2. Plan implementation (NEW - no custom commands)
claude: Please plan implementation for specs/001-user-auth/spec.md

# Claude presents dev spec for approval, then generates complete plan

# 3. Generate tasks (existing workflow)
claude: /tasks

# 4. Implement following the plan
```

## Benefits of This Approach

### ✅ **Safer Planning**
- Plan mode prevents accidental file modifications during analysis
- ExitPlanMode gives you explicit approval before any changes

### ✅ **Technology Verification**
- Claude presents tech choices upfront for your review
- No surprises about what technologies will be used
- You can override any recommendations

### ✅ **Native Integration**
- Uses Claude Code's built-in capabilities
- No custom scripts to maintain
- Works consistently across all environments

### ✅ **Flexible Interaction**
- Provide your own tech choices or let Claude suggest
- Interactive approval at each major decision point
- Full control over the planning process

## Prompt Templates

For consistency, you can copy prompts from `templates/prompts/plan-prompt.md`:

- **Guided prompts** with placeholders for your specific needs
- **Technology specification format** for clear requirements
- **Examples** for common use cases

## Constitutional Compliance

The planning process automatically follows spec-kit principles:

- **TDD**: Test-first development with red-green-refactor
- **Library-first**: Every feature as a standalone library
- **Simplicity**: Constitutional checks prevent over-engineering
- **Integration testing**: Real dependencies, comprehensive coverage

## Migration from Old `/plan` Commands

If you were using the old custom `/plan` command:

### Before (deprecated)
```bash
claude: /plan specs/001-feature/spec.md --python --fastapi
```

### After (current)
```bash
claude: Please plan implementation for specs/001-feature/spec.md using:
- Python 3.11 with FastAPI
- PostgreSQL for storage
- pytest for testing
```

The new approach provides the same functionality with better safety and user control.

## Troubleshooting

### "Claude isn't following spec-kit methodology"
Make sure to reference the spec path and ask Claude to follow spec-kit methodology in your prompt. The CLAUDE.md file provides the necessary context.

### "Technology choices weren't presented for approval"
Use Option 2 prompting style and explicitly ask Claude to "present technology choices and wait for approval before proceeding."

### "Planning artifacts weren't generated"
Ensure you're working in a feature branch (001-feature-name format) and the spec exists at the specified path.

## Support

For issues with this planning workflow:
1. Check that you're using prompts from `templates/prompts/plan-prompt.md`
2. Verify your feature branch follows the 001-feature-name format
3. Ensure your spec.md file exists and is complete
4. Review the CLAUDE.md file for the latest methodology updates