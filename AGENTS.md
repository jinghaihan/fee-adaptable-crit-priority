# Project guidelines

- Keep source, comments, scripts and documentation in English.
- Keep this an independent Cobalt mod for Leif's Adaptable; do not add menus, settings or unrelated combat changes.
- Preserve native candidate eligibility, counter range, inventory order and fallback behavior. Among counter-capable candidates, prioritize weapon critical, then the original native score.
- Keep the game/save/installations read-only during development. Use synthetic fixtures for execution tests.
- Check game version and Build ID at startup; verify exact hook contracts offline against the supplied NSO. Never gate hooks on runtime instruction equality.
- Cobalt 1.31 does not export A64InlineHook. Use only verified Cobalt imports and preserve the native register/stack contract at the comparison bridge.
- Keep README focused on behavior, requirements, installation, Credits and license; keep native contracts in docs.
- Commit changes atomically to main. Do not release or install unless explicitly requested.
