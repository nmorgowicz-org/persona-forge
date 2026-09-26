//! LAN address discovery for the Settings window's server-address list and "Copy Server
//! Address" (contract §6.4, §6.13).

use std::net::{IpAddr, Ipv4Addr};

/// Keep only non-loopback, non-link-local, non-unspecified IPv4 addresses. Pure filter, fed by
/// `if_addrs::get_if_addrs()` at the call site so this stays unit-testable without real
/// interfaces.
pub fn lan_ipv4(addrs: &[IpAddr]) -> Vec<Ipv4Addr> {
    addrs
        .iter()
        .filter_map(|addr| match addr {
            IpAddr::V4(v4) => Some(*v4),
            IpAddr::V6(_) => None,
        })
        .filter(|v4| !v4.is_loopback() && !v4.is_link_local() && !v4.is_unspecified())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_private_lan_addresses_and_drops_everything_else() {
        let addrs: Vec<IpAddr> = vec![
            "192.168.1.20".parse().unwrap(),
            "10.0.0.5".parse().unwrap(),
            "127.0.0.1".parse().unwrap(),
            "169.254.3.4".parse().unwrap(),
            "0.0.0.0".parse().unwrap(),
            "::1".parse().unwrap(),
            "fe80::1".parse().unwrap(),
        ];
        assert_eq!(
            lan_ipv4(&addrs),
            vec![
                "192.168.1.20".parse::<Ipv4Addr>().unwrap(),
                "10.0.0.5".parse::<Ipv4Addr>().unwrap()
            ]
        );
    }
}
