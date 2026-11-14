use core::{
  arch::naked_asm,
  ffi::c_void,
  sync::atomic::{AtomicUsize, Ordering},
};

use crate::{priority::Candidate, profile};

static GAME_BASE: AtomicUsize = AtomicUsize::new(0);

#[repr(C)]
struct Registers {
  x: [u64; 31],
}

pub fn install() {
  let base = unsafe { skyline::hooks::getRegionAddress(skyline::hooks::Region::Text) as usize };
  GAME_BASE.store(base, Ordering::Relaxed);
  for (offset, bridge, trampoline) in [
    (profile::COMPARE_UNIT, unit_bridge as *const c_void, &raw mut UNIT_TRAMPOLINE),
    (profile::COMPARE_SETUP, setup_bridge as *const c_void, &raw mut SETUP_TRAMPOLINE),
    (profile::COMPARE_SIDE, side_bridge as *const c_void, &raw mut SIDE_TRAMPOLINE),
  ] {
    unsafe {
      skyline::hooks::A64HookFunction((base + offset) as *const c_void, bridge, trampoline)
    };
  }
}

unsafe extern "C" fn compare(registers: &mut Registers, owner_register: usize) {
  let frame = registers.x[29] as usize;
  let score_ptr = (frame - profile::BEST_SCORE) as *mut i32;
  let index_ptr = (frame - profile::BEST_INDEX) as *mut i32;
  let previous_score = unsafe { *score_ptr };
  let previous_index = unsafe { *index_ptr };
  let score = (registers.x[19] as u32).wrapping_add(registers.x[20] as u32) as i32;
  let current = Candidate { score, critical: 0 };

  let replace = if previous_index < 0 {
    score > previous_score
  } else if current.can_counter() && previous_score & crate::priority::COUNTER_RANGE != 0 {
    let base = GAME_BASE.load(Ordering::Relaxed);
    let item_at: unsafe extern "C" fn(usize, i32, usize) -> usize =
      unsafe { core::mem::transmute(base + profile::ITEM_AT) };
    let critical: unsafe extern "C" fn(usize, usize) -> i32 =
      unsafe { core::mem::transmute(base + profile::ITEM_CRITICAL) };
    let items =
      unsafe { *((registers.x[owner_register] as usize + profile::UNIT_ITEMS) as *const usize) };
    let item = unsafe { item_at(items, previous_index, 0) };
    let previous = Candidate { score: previous_score, critical: unsafe { critical(item, 0) } };
    let current = Candidate { score, critical: unsafe { critical(registers.x[26] as usize, 0) } };
    current.preferred_to(previous)
  } else {
    current.preferred_to(Candidate { score: previous_score, critical: 0 })
  };

  if replace {
    unsafe {
      *score_ptr = score;
      *index_ptr = registers.x[24] as i32;
    }
  }
  // The relocated native block computes w19+w20 and compares it to best_score.
  // Make that comparison equal: our chosen score/index survive its two CSELs.
  // Both registers are immediately replaced by native values before loop re-entry.
  registers.x[19] = unsafe { *score_ptr } as u32 as u64;
  registers.x[20] = 0;
}

// Each compiled copy has its own continuation and receiver register. The current
// item is x26 in all three; Critical is NOT in a shared register after inlining.
macro_rules! comparison_bridge {
  ($bridge:ident, $trampoline:ident, $owner:literal) => {
    static mut $trampoline: *mut c_void = core::ptr::null_mut();

    /// Preserve the interrupted native state, then resume this site's trampoline.
    /// IP1 is dead in each independently pinned containing function.
    #[unsafe(naked)]
    unsafe extern "C" fn $bridge() {
      naked_asm!(
        "sub sp, sp, #0x300",
        "stp x0, x1, [sp, #0x00]",
        "stp x2, x3, [sp, #0x10]",
        "stp x4, x5, [sp, #0x20]",
        "stp x6, x7, [sp, #0x30]",
        "stp x8, x9, [sp, #0x40]",
        "stp x10, x11, [sp, #0x50]",
        "stp x12, x13, [sp, #0x60]",
        "stp x14, x15, [sp, #0x70]",
        "stp x16, x17, [sp, #0x80]",
        "stp x18, x19, [sp, #0x90]",
        "stp x20, x21, [sp, #0xa0]",
        "stp x22, x23, [sp, #0xb0]",
        "stp x24, x25, [sp, #0xc0]",
        "stp x26, x27, [sp, #0xd0]",
        "stp x28, x29, [sp, #0xe0]",
        "str x30, [sp, #0xf0]",
        "mrs x8, nzcv",
        "str x8, [sp, #0xf8]",
        "stp q0, q1, [sp, #0x100]",
        "stp q2, q3, [sp, #0x120]",
        "stp q4, q5, [sp, #0x140]",
        "stp q6, q7, [sp, #0x160]",
        "stp q8, q9, [sp, #0x180]",
        "stp q10, q11, [sp, #0x1a0]",
        "stp q12, q13, [sp, #0x1c0]",
        "stp q14, q15, [sp, #0x1e0]",
        "stp q16, q17, [sp, #0x200]",
        "stp q18, q19, [sp, #0x220]",
        "stp q20, q21, [sp, #0x240]",
        "stp q22, q23, [sp, #0x260]",
        "stp q24, q25, [sp, #0x280]",
        "stp q26, q27, [sp, #0x2a0]",
        "stp q28, q29, [sp, #0x2c0]",
        "stp q30, q31, [sp, #0x2e0]",
        "mov x0, sp",
        "mov x1, #{owner}",
        "bl {compare}",
        "ldp q0, q1, [sp, #0x100]",
        "ldp q2, q3, [sp, #0x120]",
        "ldp q4, q5, [sp, #0x140]",
        "ldp q6, q7, [sp, #0x160]",
        "ldp q8, q9, [sp, #0x180]",
        "ldp q10, q11, [sp, #0x1a0]",
        "ldp q12, q13, [sp, #0x1c0]",
        "ldp q14, q15, [sp, #0x1e0]",
        "ldp q16, q17, [sp, #0x200]",
        "ldp q18, q19, [sp, #0x220]",
        "ldp q20, q21, [sp, #0x240]",
        "ldp q22, q23, [sp, #0x260]",
        "ldp q24, q25, [sp, #0x280]",
        "ldp q26, q27, [sp, #0x2a0]",
        "ldp q28, q29, [sp, #0x2c0]",
        "ldp q30, q31, [sp, #0x2e0]",
        "ldr x8, [sp, #0xf8]",
        "msr nzcv, x8",
        "ldp x0, x1, [sp, #0x00]",
        "ldp x2, x3, [sp, #0x10]",
        "ldp x4, x5, [sp, #0x20]",
        "ldp x6, x7, [sp, #0x30]",
        "ldp x8, x9, [sp, #0x40]",
        "ldp x10, x11, [sp, #0x50]",
        "ldp x12, x13, [sp, #0x60]",
        "ldp x14, x15, [sp, #0x70]",
        "ldp x16, x17, [sp, #0x80]",
        "ldp x18, x19, [sp, #0x90]",
        "ldp x20, x21, [sp, #0xa0]",
        "ldp x22, x23, [sp, #0xb0]",
        "ldp x24, x25, [sp, #0xc0]",
        "ldp x26, x27, [sp, #0xd0]",
        "ldp x28, x29, [sp, #0xe0]",
        "ldr x30, [sp, #0xf0]",
        "add sp, sp, #0x300",
        "adrp x17, {trampoline}",
        "ldr x17, [x17, :lo12:{trampoline}]",
        "br x17",
        compare = sym compare,
        trampoline = sym $trampoline,
        owner = const $owner,
      );
    }
  };
}

comparison_bridge!(unit_bridge, UNIT_TRAMPOLINE, 25);
comparison_bridge!(setup_bridge, SETUP_TRAMPOLINE, 25);
comparison_bridge!(side_bridge, SIDE_TRAMPOLINE, 27);
