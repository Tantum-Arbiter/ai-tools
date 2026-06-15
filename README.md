# AI Tools

Centralised AI agent configurations for QA automation across projects using Windsurf SWE-1.6 via [windsurfinabox](https://github.com/pfcoperez/windsurfinabox).

## Projects

| Module | Type | Description |
|--------|------|-------------|
| `voiceclonenarration/` | Python / ML | Voice cloning and narration tool |
| `strickrbook/` | Mobile App | Mobile application |
| `colearn/` | Spring Boot API | Learning platform API |
| `photoshop-ai/` | Plugin / ML | Photoshop AI image processing plugin |

## Structure (per project)

```
<project>/
├── qa-instructions.md   # Windsurf QA prompt (used by windsurfinabox)
├── agent.md             # Agent behaviour and persona configuration
├── rules.md             # Coding standards and project rules
└── skills.md            # Domain-specific skills and knowledge
```

## Usage

Copy the QA instructions into your project as `windsurf-instructions.txt` before running the headless container:

```bash
cp ai-tools/voiceclonenarration/qa-instructions.md /path/to/project/windsurf-instructions.txt
```

See `delivery-plan.md` for full CI/CD integration guide.
