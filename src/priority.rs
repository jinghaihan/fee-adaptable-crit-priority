/// The native selector puts counter-range eligibility in bit 24 of its score.
pub const COUNTER_RANGE: i32 = 0x0100_0000;

#[derive(Clone, Copy, Debug)]
pub struct Candidate {
  pub score: i32,
  pub critical: i32,
}

impl Candidate {
  pub fn can_counter(self) -> bool {
    self.score & COUNTER_RANGE != 0
  }

  /// Keep the native result when neither weapon can counter or critical is tied.
  pub fn preferred_to(self, previous: Self) -> bool {
    match self.can_counter().cmp(&previous.can_counter()) {
      core::cmp::Ordering::Greater => true,
      core::cmp::Ordering::Less => false,
      core::cmp::Ordering::Equal => {
        if self.can_counter() && self.critical != previous.critical {
          self.critical > previous.critical
        } else {
          self.score > previous.score
        }
      }
    }
  }
}

#[cfg(test)]
mod tests {
  use super::*;

  fn weapon(counter: bool, critical: i32, native: i32) -> Candidate {
    Candidate { score: native + if counter { COUNTER_RANGE } else { 0 }, critical }
  }

  #[test]
  fn critical_outranks_triangle_and_effectiveness() {
    let killer = weapon(true, 40, 180);
    let effective_advantage = weapon(true, 0, 0x10_0000 + 0x1_0000 + 200);
    assert!(killer.preferred_to(effective_advantage));
    assert!(!effective_advantage.preferred_to(killer));
  }

  #[test]
  fn counter_range_outranks_any_critical() {
    let ranged = weapon(true, 0, 100);
    let melee = weapon(false, i32::MAX, 0x10_0000 + 200);
    assert!(ranged.preferred_to(melee));
    assert!(!melee.preferred_to(ranged));
  }

  #[test]
  fn equal_critical_retains_native_score_and_first_slot_ties() {
    let first = weapon(true, 35, 200);
    let advantage = weapon(true, 35, 0x10_0000 + 200);
    assert!(advantage.preferred_to(first));
    assert!(!first.preferred_to(advantage));
    assert!(!first.preferred_to(first));
  }

  #[test]
  fn no_counter_retains_native_selection() {
    let killer = weapon(false, 100, 200);
    let advantage = weapon(false, 0, 0x10_0000 + 100);
    assert!(!killer.preferred_to(advantage));
    assert!(advantage.preferred_to(killer));
  }

  #[test]
  fn critical_comparison_does_not_overflow_or_clamp() {
    let high = weapon(true, i32::MAX, 200);
    let low = weapon(true, i32::MIN, 300);
    assert!(high.preferred_to(low));
    assert!(!low.preferred_to(high));
  }
}
