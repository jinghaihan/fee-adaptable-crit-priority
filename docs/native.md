# Native comparison contract

Target: Engage 2.0.0, Build ID `8C08B9719E085F91847B5E0F935D9488`.
`tools/native-contract.json` records full-body SHA-256 fingerprints for the selector and both called native helpers. Only the 48-byte comparison continuation is included as an execution fixture; no game executable is distributed.

`Unit.GetRevengeWeapon` is at `0x01A4A4C0`. Its existing `RevengeAutoEquip` skill-flag check, attacking-unit check, inventory traversal and complete equipment/weapon eligibility checks all execute before the hook. The hook is at `0x01A4B744`, immediately after a candidate has received its native score. No candidate is added or removed by the plugin.

At this boundary:

| Native value | Location |
| --- | --- |
| Current native score | `w19 + w20` |
| Current weapon Crit, including forging/engraving/augmentation | `w22` |
| Current inventory index | `w24` |
| Unit receiver | `x25` |
| Native frame pointer | `x29` |
| Selected native score | `[x29 - 0x10]` |
| Selected inventory index, initially -1 | `[x29 - 0x0C]` |

The native score uses `0x01000000` for counter range, `0x00100000` for triangle advantage, `0x00040000` for neutral triangle interaction, and `0x00010000` for applicable effectiveness. Its remaining sum includes weapon Power, Hit, Critical, Avoid and Secure. Native stat ranges keep these fields separate.

The comparator orders by counter capability, then weapon Critical among counter-capable candidates, then the unmodified native score. Strict comparison keeps earlier inventory slots on exact ties. If neither candidate can counter, only native score is compared. The original first-candidate/fallback handling is retained.

The previous selected weapon's Crit is read with `UnitItemList.get_Item` (`0x01FB8CA0`) and `UnitItem.GetCritical` (`0x01FAF990`). Both use their native ABI with unused MethodInfo arguments set to null. GetCritical matches the selector's inlined forged/engraved/augmented Critical calculation. The selector's inventory traversal includes ordinary and available Engage weapons.

The bridge writes only the selected score and index in the current native stack frame. It then sets saved `w19` to that score and saved `w20` to zero. The original relocated comparison therefore sees equality and preserves the chosen pair. Native instructions immediately replace `x19` and `x20` before continuing the loop.

Cobalt 1.31.0 exports `A64HookFunction`, but not `A64InlineHook`. A naked AArch64 bridge preserves all integer registers, SIMD registers, NZCV and SP around the Rust comparator. IP1 (`x17`) is used for the trampoline branch; the pinned native selector has no live use of IP1. The original comparison and loop continue through Cobalt's trampoline, including relocation of the native ADRP instruction. No TLS, global candidate state, polling, inventory mutation, RNG use or skill/equipment rewriting is needed.

Startup checks the game version, rodata offset and loaded Build ID. Native instructions are verified offline, so other Cobalt hooks installed before plugin initialization do not disable this plugin through an instruction-equality gate.

## Validation

```sh
cargo test --locked
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/verify_game.py /path/to/read-only/main
cargo skyline build --release -- --locked
python3 -m pip install -r tools/test-requirements.txt
python3 scripts/smoke.py target/aarch64-skyline-switch/release/libfee_leif_crit_priority.nro
```

The compiled-NRO sandbox exercises startup compatibility rejection, the comparison bridge, native stack-slot updates and a relocated native continuation. It checks register/SIMD/stack preservation even when native helper fixtures destroy volatile registers. Selection cases cover both inventory orders, ranged versus melee weapons, higher critical versus triangle/effectiveness, tied critical, exact ties, no-counter fallback, all eight native slots and randomized candidate lists. Native candidate eligibility is retained structurally; these fixtures do not claim a live-game playtest or a complete combat simulation.

The plugin does not calculate expected critical damage, final enemy-adjusted critical rate, doubling or kill probability. Compatibility with another mod replacing the same comparison block is not established.
