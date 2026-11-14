#![deny(unsafe_op_in_unsafe_fn)]

pub mod priority;
pub mod profile;

#[cfg(target_os = "switch")]
mod native;

#[cfg(target_os = "switch")]
#[skyline::main(name = "leifcrit")]
pub fn skyline_main() {
  if supported_game() {
    native::install();
  }
}

#[cfg(target_os = "switch")]
fn supported_game() -> bool {
  use skyline::hooks::{getRegionAddress, Region};
  let mut version = skyline::nn::oe::DisplayVersion { name: [0; 16] };
  unsafe { skyline::nn::oe::GetDisplayVersion(&mut version) };
  if version.name[..6] != [b'2', b'.', b'0', b'.', b'0', 0] {
    return false;
  }
  let base = unsafe { getRegionAddress(Region::Text) as usize };
  let rodata = unsafe { getRegionAddress(Region::Rodata) as usize };
  if base == 0 || rodata.checked_sub(base) != Some(profile::RODATA_OFFSET) {
    return false;
  }
  unsafe {
    core::slice::from_raw_parts((base + profile::BUILD_ID_OFFSET) as *const u8, 16)
      == profile::BUILD_ID
  }
}
