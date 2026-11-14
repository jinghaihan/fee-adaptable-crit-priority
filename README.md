# FEE Adaptable Crit Priority

Make Leif's **Adaptable** favor high-critical weapons in **Fire Emblem Engage**.

## Features

- Keep counterattack range first, then prefer the weapon with higher Crit over weapon-triangle advantage and effectiveness.
- Include forged, engraved and augmented weapon Crit.
- Keep the original weapon scoring when Crit is equal, including inventory order for exact ties.
- Keep the original selection when no eligible weapon can counterattack.
- Retain the game's equipment restrictions and Adaptable activation rules.
- Always active while installed, with no settings or additional menus.

Weapon Crit is the weapon's stat, rather than the final combat critical rate. Critical rates and damage are unchanged.

## Requirements

- Fire Emblem Engage **2.0.0**.
- [Cobalt **1.31.0**](https://github.com/Raytwo/Cobalt/releases/tag/v1.31.0).

## Installation

Download the ZIP from [Releases](https://github.com/jinghaihan/fee-adaptable-crit-priority/releases/latest).

### Nintendo Switch

Install Cobalt, then extract the ZIP's `engage` directory at the SD card root.

### Emulators

Extract `engage` into the emulator's virtual SD card root.

Installed path: `engage/mods/fee_adaptable_crit_priority/fee_adaptable_crit_priority.nro`.
Fully restart the game after installation or removal. This mod does not write save data.

## Credits

- [Cobalt](https://github.com/Raytwo/Cobalt) and [skyline-rs](https://github.com/ultimate-research/skyline-rs) — loader and runtime.
- [engage-il2cpp](https://github.com/DivineDragonFanClub/engage-il2cpp) — native interface references.

Unofficial fan project, not affiliated with Nintendo or Intelligent Systems.

## License

[MIT](LICENSE).
