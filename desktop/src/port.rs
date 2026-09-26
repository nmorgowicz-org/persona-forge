//! Port selection (contract §6.3, D11). `select_port` is a pure function: the caller supplies a
//! `probe` closure so the whole policy is unit-testable without binding real sockets.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortState {
    Free,
    PersonaForge,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortMode {
    Auto,
    Fixed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortDecision {
    /// Use this port; nothing else to tell the user.
    Use(u16),
    /// Auto mode moved off a busy persisted port; show the one-time "port moved" notification.
    Moved { from: u16, to: u16 },
    /// The persisted (or first-scanned) port already answers as Persona Forge: do not start a
    /// second server against the same state dir.
    ExternalPersonaForge(u16),
    /// Fixed mode never moves off a busy port; show the "port in use" dialog.
    FixedPortBusy(u16),
    /// Nothing in the scan range was free.
    NoneFree,
}

const AUTO_SCAN_RANGE: std::ops::RangeInclusive<u16> = 8318..=8348;

/// `probe(port)` is the port's state per contract §6.3 (bind-test, else `/health`).
pub fn select_port(
    mode: PortMode,
    persisted: Option<u16>,
    probe: impl Fn(u16) -> PortState,
) -> PortDecision {
    if let Some(port) = persisted {
        match probe(port) {
            PortState::Free => return PortDecision::Use(port),
            PortState::PersonaForge => return PortDecision::ExternalPersonaForge(port),
            PortState::Other => match mode {
                PortMode::Fixed => return PortDecision::FixedPortBusy(port),
                PortMode::Auto => {
                    return match scan_for_free(&probe) {
                        ScanResult::Free(next) => PortDecision::Moved {
                            from: port,
                            to: next,
                        },
                        ScanResult::ExternalPersonaForge(p) => {
                            PortDecision::ExternalPersonaForge(p)
                        }
                        ScanResult::NoneFree => PortDecision::NoneFree,
                    };
                }
            },
        }
    }

    // First run: no persisted port. Contract §6.3 step 4 applies in both modes the same way
    // (there is nothing to "fix" yet), scanning from the start of the range.
    match scan_for_free(&probe) {
        ScanResult::Free(port) => PortDecision::Use(port),
        ScanResult::ExternalPersonaForge(port) => PortDecision::ExternalPersonaForge(port),
        ScanResult::NoneFree => PortDecision::NoneFree,
    }
}

enum ScanResult {
    Free(u16),
    ExternalPersonaForge(u16),
    NoneFree,
}

fn scan_for_free(probe: &impl Fn(u16) -> PortState) -> ScanResult {
    for port in AUTO_SCAN_RANGE {
        match probe(port) {
            PortState::Free => return ScanResult::Free(port),
            PortState::PersonaForge => return ScanResult::ExternalPersonaForge(port),
            PortState::Other => continue,
        }
    }
    ScanResult::NoneFree
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn probe_from(states: &HashMap<u16, PortState>) -> impl Fn(u16) -> PortState + '_ {
        move |port| states.get(&port).copied().unwrap_or(PortState::Free)
    }

    #[test]
    fn auto_persisted_free_uses_it() {
        let states = HashMap::from([(8318, PortState::Free)]);
        assert_eq!(
            select_port(PortMode::Auto, Some(8318), probe_from(&states)),
            PortDecision::Use(8318)
        );
    }

    #[test]
    fn auto_persisted_persona_forge_is_external() {
        let states = HashMap::from([(8318, PortState::PersonaForge)]);
        assert_eq!(
            select_port(PortMode::Auto, Some(8318), probe_from(&states)),
            PortDecision::ExternalPersonaForge(8318)
        );
    }

    #[test]
    fn auto_persisted_other_with_next_port_free_moves() {
        let states = HashMap::from([(8318, PortState::Other), (8319, PortState::Free)]);
        assert_eq!(
            select_port(PortMode::Auto, Some(8318), probe_from(&states)),
            PortDecision::Moved {
                from: 8318,
                to: 8319
            }
        );
    }

    #[test]
    fn fixed_persisted_other_never_moves() {
        let states = HashMap::from([(9123, PortState::Other), (8319, PortState::Free)]);
        assert_eq!(
            select_port(PortMode::Fixed, Some(9123), probe_from(&states)),
            PortDecision::FixedPortBusy(9123)
        );
    }

    #[test]
    fn first_run_8318_answering_as_persona_forge_never_starts_a_second_server() {
        let states = HashMap::from([(8318, PortState::PersonaForge)]);
        assert_eq!(
            select_port(PortMode::Auto, None, probe_from(&states)),
            PortDecision::ExternalPersonaForge(8318)
        );
    }

    #[test]
    fn first_run_8318_busy_8319_free_uses_8319() {
        let states = HashMap::from([(8318, PortState::Other), (8319, PortState::Free)]);
        assert_eq!(
            select_port(PortMode::Auto, None, probe_from(&states)),
            PortDecision::Use(8319)
        );
    }

    #[test]
    fn all_busy_is_none_free() {
        let mut states = HashMap::new();
        for port in 8318u16..=8348 {
            states.insert(port, PortState::Other);
        }
        assert_eq!(
            select_port(PortMode::Auto, None, probe_from(&states)),
            PortDecision::NoneFree
        );
        assert_eq!(
            select_port(PortMode::Fixed, None, probe_from(&states)),
            PortDecision::NoneFree
        );
    }

    #[test]
    fn fixed_mode_first_run_scans_like_auto() {
        let states = HashMap::from([(8318, PortState::Other), (8319, PortState::Free)]);
        assert_eq!(
            select_port(PortMode::Fixed, None, probe_from(&states)),
            PortDecision::Use(8319)
        );
    }
}
