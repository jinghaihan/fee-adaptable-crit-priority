#!/usr/bin/env python3
"""Execute the compiled NRO and comparison bridge with modeled native boundaries.

Requires unicorn==2.1.4. No game executable or save is needed for these fixtures.
"""

import argparse
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as reg

from nro_imports import required_imports
from verify_nro import verify_nro


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "tools/native-contract.json").read_text())
BASE, GAME, STUB, STACK = 0x100000000, 0x200000000, 0x300000000, 0x400000000
STOP, TRAMPOLINE = STUB + 0xF000, STUB + 0xD000
SITES = CONTRACT["comparisons"]
COUNTER = 0x1000000


class NativeBoundsError(RuntimeError):
  """The unmodified UnitItemList getter reached its native out-of-range path."""


def metadata(data):
  mod, = struct.unpack_from("<I", data, 4)
  relative, = struct.unpack_from("<i", data, mod + 4)
  cursor, tags = mod + relative, {}
  while True:
    tag, value = struct.unpack_from("<QQ", data, cursor)
    cursor += 16
    if not tag:
      break
    tags[tag] = value
  count, = struct.unpack_from("<I", data, tags[4] + 4)
  symbols = []
  for index in range(count):
    name, _, _, section, value, _ = struct.unpack_from("<IBBHQQ", data, tags[6] + index * 24)
    start = tags[5] + name
    symbols.append((data[start:data.index(0, start)].decode(), section, value))
  relocations = []
  for table, size in ((7, 8), (23, 2)):
    if table in tags:
      for cursor in range(tags[table], tags[table] + tags[size], 24):
        relocations.append(struct.unpack_from("<QQq", data, cursor))
  return symbols, relocations


def adrp(register, pc, target):
  delta = ((target & ~0xFFF) - (pc & ~0xFFF)) >> 12
  assert -(1 << 20) <= delta < (1 << 20)
  return 0x90000000 | ((delta & 3) << 29) | (((delta >> 2) & 0x7FFFF) << 5) | register


class Sandbox:
  def __init__(self, data, case="supported", legacy=False):
    self.cpu = cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    self.case, self.hooks, self.calls, self.pages = case, [], [], set()
    self.expected_registers = None
    self.items, self.critical = {}, {}
    symbols, relocations = metadata(data)
    main = next(value for name, section, value in symbols if name == "main" and section)
    size = (len(data) + struct.unpack_from("<I", data, 0x38)[0] + 0xFFF) & ~0xFFF
    cpu.mem_map(BASE, size)
    cpu.mem_write(BASE, data)
    cpu.mem_map(STUB, 0x10000)
    cpu.mem_map(STACK, 0x20000)
    imports = {name: STUB + index * 16 for index, name in enumerate(sorted(required_imports(data)))}
    self.imports = {address: name for name, address in imports.items()}
    for target, info, addend in relocations:
      index, kind = info >> 32, info & 0xFFFFFFFF
      if kind == 1027:
        value = BASE + addend
      elif kind in (257, 1025, 1026):
        name, section, value = symbols[index]
        value = imports[name] if not section else value + (0 if section == 0xFFF1 else BASE)
        value += addend
      else:
        raise AssertionError(f"unexpected relocation {kind}")
      cpu.mem_write(BASE + target, struct.pack("<Q", value))
    self.write(GAME + 0x5D7B20C, bytes(16) if case == "wrong_build" else bytes.fromhex(CONTRACT["build_id"]))
    self.trampolines = {}
    for index, site in enumerate(SITES):
      trampoline = TRAMPOLINE + index * 0x100
      self.trampolines[trampoline] = site
      comparison = bytes.fromhex(site["bytes"])
      self.write(GAME + site["offset"], comparison)
      self.write(GAME + site["arrival"], bytes.fromhex(site["arrival_bytes"]))
      if case == "prehooked":
        self.write(GAME + site["offset"], struct.pack("<I", 0x14000000))
      copied = bytearray(comparison[:20])
      struct.pack_into("<I", copied, site["adrp_offset"],
                       adrp(site["adrp_register"], trampoline + site["adrp_offset"], GAME + 0x6284000))
      copied += struct.pack("<IIQ", 0x58000051, 0xD61F0220, GAME + site["offset"] + 20)
      cpu.mem_write(trampoline, bytes(copied))
      self.write(GAME + site["loop_resume"], bytes(4))
    self.write(GAME + CONTRACT["item_at_offset"], bytes.fromhex(CONTRACT["item_at_bytes"]))
    self.write(GAME + CONTRACT["item_critical_offset"], bytes(4))
    self.write(GAME + 0x492290, bytes(4))
    save = CONTRACT["setup_owner_save"]
    self.write(GAME + save["offset"], bytes.fromhex(save["bytes"]))
    for address, value in ((0x6284190, 0x12345678), (0x6284188, 0x23456789), (0x62840C8, 0x3456789A)):
      self.write(GAME + address, struct.pack("<Q", value))
    cpu.hook_add(UC_HOOK_CODE, self.on_code)
    cpu.reg_write(reg.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    cpu.reg_write(reg.UC_ARM64_REG_SP, STACK + 0x1F000)
    cpu.reg_write(reg.UC_ARM64_REG_X30, STOP)
    self.run(BASE + main, STOP)
    expected = [] if case.startswith("wrong_") else [GAME + site["offset"] for site in SITES]
    if legacy:
      expected = expected[:1]
    assert [target for target, _ in self.hooks] == expected, (case, self.hooks)

  def write(self, address, data):
    for page in range(address & ~0xFFF, (address + len(data) + 0xFFF) & ~0xFFF, 0x1000):
      if page not in self.pages:
        self.cpu.mem_map(page, 0x1000)
        self.pages.add(page)
    self.cpu.mem_write(address, data)

  def x(self, index):
    return self.cpu.reg_read(getattr(reg, f"UC_ARM64_REG_X{index}"))

  def return_value(self, value=None):
    if value is not None:
      self.cpu.reg_write(reg.UC_ARM64_REG_X0, value & 0xFFFFFFFFFFFFFFFF)
    # Native callees may destroy all volatile scalar/SIMD registers.
    for index in range(1, 19):
      self.cpu.reg_write(getattr(reg, f"UC_ARM64_REG_X{index}"), 0xBAD00000 + index)
    for index in (*range(8), *range(16, 32)):
      self.cpu.reg_write(getattr(reg, f"UC_ARM64_REG_Q{index}"), 0xBAD00000 + index)
    for index in range(8, 16):
      register = getattr(reg, f"UC_ARM64_REG_Q{index}")
      low = self.cpu.reg_read(register) & 0xFFFFFFFFFFFFFFFF
      self.cpu.reg_write(register, low | ((0xBAD00000 + index) << 64))
    self.cpu.reg_write(reg.UC_ARM64_REG_PC, self.x(30))

  def on_code(self, cpu, address, size, _):
    if address in self.trampolines and self.expected_registers is not None:
      expected, simd, stack, flags = self.expected_registers
      for index in range(31):
        if index not in (17, 19, 20):
          assert self.x(index) == expected[index], ("register", index)
      for index in range(32):
        assert cpu.reg_read(getattr(reg, f"UC_ARM64_REG_Q{index}")) == simd[index], ("SIMD", index)
      assert cpu.reg_read(reg.UC_ARM64_REG_SP) == stack
      assert cpu.reg_read(reg.UC_ARM64_REG_NZCV) == flags
      return
    if address == GAME + CONTRACT["item_at_offset"]:
      assert self.x(2) == 0
      index = self.x(1)
      self.calls.append(("item", index))
      # Execute the real getter and its array bound check. A metadata object
      # passed as Unit must fail here, rather than being accepted by a stub.
      return
    if address == GAME + 0x492290:
      raise NativeBoundsError("UnitItemList.get_Item: native array index out of range")
    if address == GAME + CONTRACT["item_critical_offset"]:
      assert self.x(1) == 0
      item = self.x(0)
      self.calls.append(("critical", item))
      self.return_value(self.critical[item])
      return
    name = self.imports.get(address)
    if not name:
      return
    if name == "getRegionAddress":
      self.return_value(GAME if self.x(0) == 0 else GAME + 0x3F48000 + (0x1000 if self.case == "wrong_layout" else 0))
    elif name == "_ZN2nn2oe17GetDisplayVersionEPNS0_14DisplayVersionE":
      cpu.mem_write(self.x(0), b"1.3.0\0" if self.case == "wrong_version" else b"2.0.0\0")
      self.return_value()
    elif name == "A64HookFunction":
      target, bridge = self.x(0), self.x(1)
      index = next(i for i, site in enumerate(SITES) if GAME + site["offset"] == target)
      self.hooks.append((target, bridge))
      # Exercise a real incoming native branch into the installed far jump, not
      # a direct call to the replacement (which missed the inlined callers).
      cpu.mem_write(target, struct.pack("<IIIQ", 0xD503201F, 0x58000051, 0xD61F0220, bridge))
      cpu.mem_write(self.x(2), struct.pack("<Q", TRAMPOLINE + index * 0x100))
      self.return_value()
    elif name == "memcmp":
      a, b, length = self.x(0), self.x(1), self.x(2)
      left, right = bytes(cpu.mem_read(a, length)), bytes(cpu.mem_read(b, length))
      self.return_value(int(left > right) - int(left < right))
    elif name == "memset":
      cpu.mem_write(self.x(0), bytes([self.x(1) & 0xFF]) * self.x(2))
      self.return_value()
    elif name in ("memcpy", "memmove"):
      cpu.mem_write(self.x(0), bytes(cpu.mem_read(self.x(1), self.x(2))))
      self.return_value()
    else:
      raise AssertionError(f"unexpected runtime import: {name}")

  def run(self, address, stop):
    self.cpu.emu_start(address, stop, count=100_000)
    assert self.cpu.reg_read(reg.UC_ARM64_REG_PC) == stop, "execution did not reach the native continuation"

  def select(self, candidates, site_index=0):
    cpu = self.cpu
    owner, items = GAME + 0x7001000, GAME + 0x7002000
    self.write(owner + 0xB8, struct.pack("<Q", items))
    array, metadata, invalid_list, empty_array = [GAME + n for n in (0x7003000, 0x7004000, 0x7005000, 0x7006000)]
    self.write(items + 0x10, struct.pack("<Q", array))
    self.write(array + 0x18, struct.pack("<Q", 8))
    self.write(array + 0x20, bytes(8 * 8))
    # Real SetupScope x25 holds calculator metadata. Give it a distinct,
    # readable layout whose mistaken Unit-item-list read has zero capacity.
    self.write(metadata + 0xB8, struct.pack("<Q", invalid_list))
    self.write(invalid_list + 0x10, struct.pack("<Q", empty_array))
    self.write(empty_array + 0x18, bytes(8))
    site = SITES[site_index]
    frame = STACK + 0x1E000
    stack = frame - site["frame_offset"]
    cpu.mem_write(frame - 16, struct.pack("<ii", -1, -1))
    cpu.mem_write(stack + 24, struct.pack("<QQ", 0x87654321, 0x98765432))
    if site_index == 1:
      cpu.reg_write(reg.UC_ARM64_REG_X27, owner)
      cpu.reg_write(reg.UC_ARM64_REG_SP, stack)
      # Execute the constructor's actual STR x27,[sp,#0x20].
      save = CONTRACT["setup_owner_save"]
      self.run(GAME + save["offset"], GAME + save["offset"] + 4)
    self.items, self.critical = {}, {}
    for index, (score, critical) in enumerate(candidates):
      item = GAME + 0x7100000 + index * 0x100
      self.items[index], self.critical[item] = item, critical
      self.write(array + 0x20 + index * 8, struct.pack("<Q", item))
      for n in range(31):
        cpu.reg_write(getattr(reg, f"UC_ARM64_REG_X{n}"), 0xA0000000 + n)
      for n in range(32):
        cpu.reg_write(getattr(reg, f"UC_ARM64_REG_Q{n}"), (n + 1) * 0x123456789ABCDEF123456789ABCDEF)
      for n, value in ((19, score), (20, 0), (22, critical), (24, index), (25, owner), (29, frame)):
        cpu.reg_write(getattr(reg, f"UC_ARM64_REG_X{n}"), value & 0xFFFFFFFF)
      # Keep the caller's Unit and calculator metadata distinct. SetupScope
      # recovers Unit from its saved stack slot, never from metadata in x25.
      cpu.reg_write(reg.UC_ARM64_REG_X0, 0)  # native CBZ from the no-augmentation path
      cpu.reg_write(reg.UC_ARM64_REG_X22, 0xDEAD2222)
      cpu.reg_write(reg.UC_ARM64_REG_X25, metadata)
      cpu.reg_write(reg.UC_ARM64_REG_X26, item)
      if "owner_register" in site:
        cpu.reg_write(getattr(reg, f"UC_ARM64_REG_X{site['owner_register']}"), owner)
      cpu.reg_write(reg.UC_ARM64_REG_X29, frame)
      cpu.reg_write(reg.UC_ARM64_REG_SP, stack)
      cpu.reg_write(reg.UC_ARM64_REG_NZCV, 0xA0000000)
      self.expected_registers = (
        [self.x(n) for n in range(31)],
        [cpu.reg_read(getattr(reg, f"UC_ARM64_REG_Q{n}")) for n in range(32)],
        stack, 0xA0000000,
      )
      self.run(GAME + site["arrival"], GAME + site["loop_resume"])
      assert cpu.reg_read(reg.UC_ARM64_REG_SP) == stack
      assert self.x(20) == (metadata if site_index == 1 else owner)
      assert self.x(21) == 0x87654321
      assert self.x(19) == (0x12345678 if site_index == 0 else 0x23456789)
      if site_index == 1:
        assert self.x(25) == 0x3456789A
        assert self.x(27) == owner
      elif site_index == 2:
        assert self.x(27) == 0x12345678
    score, index = struct.unpack("<ii", cpu.mem_read(frame - 16, 8))
    if index >= 0:
      assert score == candidates[index][0], "native score was corrupted"
    return index


def panette_weapons(distance):
  return [
    ((COUNTER if distance == 1 else 0) + 0x40000 + 200, 50),
    ((COUNTER if distance == 2 else 0) + 0x40000 + 200, 50),
    ((COUNTER if distance == 1 else 0) + 0x40000 + 180, 30),
    (COUNTER + 150, 0),
    (COUNTER + 0x100000 + 180, 20),
  ]


def exercise(data):
  for case in ("supported", "wrong_version", "wrong_build", "wrong_layout", "prehooked"):
    Sandbox(data, case)
  sandbox = Sandbox(data)
  cases = [
    ([(COUNTER + 0x100000 + 200, 0), (COUNTER + 180, 40)], 1),
    ([(COUNTER + 180, 40), (COUNTER + 0x100000 + 200, 0)], 0),
    ([(0x100000 + 200, 100), (COUNTER + 100, 0)], 1),
    ([(COUNTER + 100, 0), (0x100000 + 200, 100)], 0),
    ([(COUNTER + 200, 35), (COUNTER + 0x100000 + 180, 35)], 1),
    ([(COUNTER + 200, 35), (COUNTER + 200, 35)], 0),
    ([(0x100000 + 100, 0), (200, 100)], 0),
    ([(200, 100), (0x100000 + 100, 0)], 1),
    ([(COUNTER + 0x10000 + 300, 30), (COUNTER + 100, 31)], 1),
    ([(COUNTER + 300, 10), (COUNTER + 200, 50), (COUNTER + 0x100000 + 500, 20)], 1),
    ([(COUNTER + 100 + n, n) for n in range(8)], 7),
    ([], -1),
  ]
  # Panette + Leif: two personal killer weapons and three Engage weapons.
  # Against an axe, vanilla Light Brand wins triangle priority at either range.
  for distance, expected in ((1, 0), (2, 1)):
    cases.append((panette_weapons(distance), expected))
  for site_index in range(len(SITES)):
    for candidates, expected in cases:
      assert sandbox.select(candidates, site_index) == expected, (SITES[site_index]["name"], candidates, expected)
  # Replay varied forged/engraved critical and native scores in both slot orders.
  import random
  rng = random.Random(0x1E1F)
  for _ in range(100):
    candidates = [(rng.choice((0, COUNTER)) + rng.choice((0, 0x40000, 0x100000))
                   + rng.choice((0, 0x10000)) + rng.randrange(100, 500), rng.randrange(-30, 150))
                  for _ in range(rng.randrange(1, 9))]
    def key(i):
      score, critical = candidates[i]
      counter = bool(score & COUNTER)
      return counter, critical if counter else 0, score, -i
    expected = max(range(len(candidates)), key=key)
    for site_index in range(len(SITES)):
      assert sandbox.select(candidates, site_index) == expected
  print("Compiled NRO: 5 startup cases, 342 selection cases across all 3 compiled copies, native incoming branches and relocated continuations and integer/SIMD/stack preservation passed")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("nro", type=Path)
  parser.add_argument("--regression-before", type=Path, help="also reproduce the missing inlined hooks using an actual v0.1.1 NRO")
  parser.add_argument("--regression-crash-before", type=Path, help="reproduce the wrong SetupScope receiver using an actual v0.1.2 NRO")
  args = parser.parse_args()
  verify_nro(args.nro)
  if args.regression_before:
    verify_nro(args.regression_before)
    before = Sandbox(args.regression_before.read_bytes(), legacy=True)
    for site_index in (1, 2):
      for distance in (1, 2):
        assert before.select(panette_weapons(distance), site_index) == 4
    print("Actual v0.1.1 NRO reproduces Light Brand selection at 1 and 2 range in both inlined callers")
  if args.regression_crash_before:
    verify_nro(args.regression_crash_before)
    for distance in (1, 2):
      before = Sandbox(args.regression_crash_before.read_bytes())
      try:
        before.select(panette_weapons(distance), 1)
      except NativeBoundsError:
        pass
      else:
        raise AssertionError("v0.1.2 failed to reproduce the native bounds exception")
    print("Actual v0.1.2 NRO reproduces the logged UnitItemList.get_Item bounds exception with real SetupScope metadata/Unit separation")
  exercise(args.nro.read_bytes())
