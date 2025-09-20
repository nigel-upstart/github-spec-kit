# Spec-Kit Planning Prompt Template

Use this prompt template when asking Claude Code to plan feature implementation:

## Option 1: Provide Your Technology Choices

```
Please create an implementation plan for the feature specification at: specs/[BRANCH]/spec.md

Use these technology choices:
- Language/Version: [e.g., Python 3.11, TypeScript 5.0]
- Primary Dependencies: [e.g., FastAPI, React, Express]
- Storage: [e.g., PostgreSQL, Redis, filesystem, N/A]
- Testing Framework: [e.g., pytest, Jest, vitest]
- Target Platform: [e.g., Linux server, browser, mobile]
- Performance Goals: [e.g., 1000 req/s, <200ms p95]
- Constraints: [e.g., memory limits, offline capability]

Follow the spec-kit plan template to generate all required artifacts and present the complete implementation plan for my approval.
```

## Option 2: Let Claude Suggest Technology Choices

```
Please create an implementation plan for the feature specification at: specs/[BRANCH]/spec.md

First, generate a Development Specification with your recommended technology choices:
- Language/Version (e.g., Python 3.11, TypeScript 5.0)
- Primary Dependencies (e.g., FastAPI, React, Express)
- Storage (e.g., PostgreSQL, Redis, filesystem)
- Testing Framework (e.g., pytest, Jest, vitest)
- Target Platform (e.g., Linux server, browser, mobile)
- Performance Goals (e.g., 1000 req/s, <200ms p95)
- Constraints (e.g., memory limits, offline capability)

Present these choices and wait for my approval or modifications before proceeding.

Once approved, follow the spec-kit plan template to:
1. Research and resolve any NEEDS CLARIFICATION markers
2. Generate design artifacts (research.md, data-model.md, contracts/, quickstart.md)
3. Verify constitution compliance (TDD, library-first, simplicity)
4. Describe task generation approach (without creating tasks.md)
5. Present the complete implementation plan for my final approval
```

## Usage Instructions

1. Replace `[BRANCH]` with your actual feature branch name (e.g., `001-user-auth`)
2. For Option 1: Fill in your specific technology choices
3. For Option 2: Use as-is and Claude will suggest technologies
4. Claude will automatically enter plan mode and use the spec-kit methodology
5. Review and approve the development specification before full planning begins
6. Review and approve the final implementation plan before execution

## What Claude Will Generate

Following the spec-kit plan template, Claude will create:
- **Development Specification**: Technology stack and constraints (verified with you)
- **research.md**: Research findings for any unclear aspects
- **data-model.md**: Entity definitions and relationships
- **contracts/**: API contracts and specifications
- **quickstart.md**: Step-by-step validation procedures
- **Complete Implementation Plan**: With constitution checks and task approach

The planning follows spec-kit constitutional principles: TDD, library-first architecture, simplicity, and proper testing strategies.