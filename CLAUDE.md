## Git

This repo is pushed to https://github.com/HerocalypseDev/jarvis-main2 (private). Push changes
after every phase of work (each meaningful chunk — a feature, a fix, a batch of related
changes), not only when explicitly asked: commit with a clear message and `git push`. Review
`git status`/`git diff` before staging, and never commit anything that looks like a real
credential, token, or PIN (check new files under `skills/` in particular — a skill can contain
things like typed passcodes). `jarvis_assistant/` is a separate, unrelated project and stays
out of this repo's history.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
