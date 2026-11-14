# Native comparison contracts

Target: Engage 2.0.0, Build ID `8C08B9719E085F91847B5E0F935D9488`.

The compiler emitted the Adaptable selector three times. Hooking the public method alone does not cover the inlined battle paths; no direct BL call to its public body exists in the supplied text segment.

| Containing method | Comparison | Receiver | Candidate item |
| --- | --- | --- | --- |
| Unit.GetRevengeWeapon | `0x01A4B744` | x25 | x26 |
| BattleInfo.SetupScope constructor | `0x019B9624` | original sp+0x20 (fp-0x50) | x26 |
| BattleInfoSide.ComplementConditions | `0x01E8045C` | x27 | x26 |

`tools/native-contract.json` pins each containing method and both native getters with full-body SHA-256 fingerprints. It independently records comparison continuations, incoming native branches, receiver registers/saved-stack locations, frame offsets, relocated ADRP registers and the constructor instruction that saves Unit. The offline verifier searches for all occurrences of the comparison prefix and rejects incomplete coverage. No game executable is distributed.

In each copy, existing skill flags, attacking-unit checks, inventory traversal and complete equipment/weapon eligibility execute before the comparison. The plugin does not add or remove candidates. Their shared boundary has native score `w19 + w20`, inventory index `w24`, frame pointer `x29`, selected score `[x29 - 0x10]` and selected index `[x29 - 0x0C]`. Critical is not held in a shared register: the setup copy reuses x22 for outer state, while the conditions copy computes Critical in w25. SetupScope x25 preserves outer calculator metadata, not Unit: the original constructor saves Unit with STR x27,[sp,#0x20] and reloads it with LDP x21,x27,[sp,#0x18]. The bridge obtains that saved pointer through the original frame pointer.

The comparator reads both weapons' Critical through UnitItem.GetCritical (`0x01FAF990`). The previous item comes from UnitItemList.get_Item (`0x01FB8CA0`) and the site's receiver. The current item is x26. Both getters use their native ABI with unused MethodInfo arguments set to null. GetCritical includes the same forged, engraved and augmented Critical calculation as the native selectors.

The native score uses `0x01000000` for counter range, `0x00100000` for triangle advantage, `0x00040000` for neutral triangle interaction, and `0x00010000` for applicable effectiveness. Its remaining sum includes weapon Power, Hit, Critical, Avoid and Secure. Native stat ranges keep these fields separate.

Selection orders by counter capability, then weapon Critical among counter-capable candidates, then the unmodified native score. Strict comparison retains earlier inventory slots on exact ties. If neither candidate can counter, only native score is compared. The original first-candidate/fallback handling remains intact.

Each site has its own Cobalt trampoline. A shared naked AArch64 bridge preserves integer/SIMD registers, NZCV and SP around the Rust comparator. IP1 (x17) is branch scratch and is dead in all three pinned containing functions. The callback updates only the current native frame's selected score/index, then makes the relocated native comparison equal so its CSELs retain that pair. The native continuation replaces the modified temporary w19/w20 before loop re-entry.

Cobalt 1.31.0 exports A64HookFunction, not A64InlineHook. The bridge uses the former, with ADRP relocation handled by the original trampoline. No TLS, global candidate state, polling, inventory mutation, RNG use or skill/equipment rewriting is needed. Startup checks game version, rodata offset and loaded Build ID; instruction contracts are checked offline rather than gated by runtime instruction equality.

## Validation

```sh
cargo test --locked
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/verify_game.py /path/to/read-only/main
cargo skyline build --release -- --locked
python3 -m pip install -r tools/test-requirements.txt
python3 scripts/smoke.py target/aarch64-skyline-switch/release/libfee_adaptable_crit_priority.nro
```

The compiled-NRO sandbox enters all three sites through native incoming branches and installed far jumps, then executes relocated native continuations. It validates register/SIMD/stack preservation under volatile-register destruction by native getter fixtures. Tests keep Unit and calculator metadata as distinct objects. The setup fixture executes the original Unit-saving instruction; metadata has a separate layout that fails if mistaken for Unit. The actual native UnitItemList.get_Item body executes its real array-capacity check, rather than accepting a mocked receiver.

The user-reported Panette/Leif regression uses Killer Axe, Killer Bow and the three Engage weapons against an axe: one-range selects Killer Axe; two-range selects Killer Bow. Replaying the published v0.1.1 NRO through both inlined paths reproduces Light Brand selection at both distances. This before/after check is available with `--regression-before /path/to/v0.1.1.nro`; old binaries are not vendored.

The reported v0.1.2 enemy-turn failure was an out-of-range exception from UnitItemList.get_Item, reached through plugin offset 0x484. v0.1.2 misread SetupScope x25 calculator metadata as Unit. Replaying the published v0.1.2 NRO with distinct metadata and Unit layouts reproduces the native bounds exception; the corrected saved-stack receiver passes. Use `--regression-crash-before /path/to/v0.1.2.nro` for this check.

The suite covers 5 startup cases and 342 candidate-selection cases over the three compiled copies, including native tie order, counter priority, all eight slots and randomized inventories. Native eligibility is preserved structurally. This is not a live-game playtest or complete combat simulation.

The plugin does not calculate expected critical damage, final enemy-adjusted critical rate, doubling or kill probability. Compatibility with another mod replacing the same comparison blocks is not established.
