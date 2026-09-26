//! Strict argument parsing (contract §6.8), run before anything else — including
//! single-instance — so `--smoke-test` and CI's `--ci-update` never wait on a lock held by a
//! GUI instance.

use std::path::PathBuf;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Args {
    Gui,
    SmokeTest(PathBuf),
    #[cfg(feature = "ci-hooks")]
    CiUpdate(PathBuf),
}

/// Exit code for an unknown `--` flag (contract §6.8). Tests and guards check this code, not
/// stderr text, because the release Windows exe has no console.
pub const EXIT_UNKNOWN_ARGUMENT: i32 = 2;

/// `Err(exit_code)` on an unknown flag (the caller should print `unknown argument: <flag>` to
/// stderr, then exit with the code). OS-supplied non-flag arguments (for example a macOS
/// `-psn_…` argument) are ignored, not rejected.
pub fn parse<I: IntoIterator<Item = String>>(args: I) -> Result<Args, (String, i32)> {
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        if arg == "--smoke-test" {
            let out = iter
                .next()
                .ok_or_else(|| (arg.clone(), EXIT_UNKNOWN_ARGUMENT))?;
            return Ok(Args::SmokeTest(PathBuf::from(out)));
        }
        #[cfg(feature = "ci-hooks")]
        if arg == "--ci-update" {
            let out = iter
                .next()
                .ok_or_else(|| (arg.clone(), EXIT_UNKNOWN_ARGUMENT))?;
            return Ok(Args::CiUpdate(PathBuf::from(out)));
        }
        if arg.starts_with("--") {
            // `--ci-update` without the feature: contract §6.8 says this is unknown, not
            // silently ignored, so a release build always rejects it (release-smoke checks
            // this exact exit code).
            return Err((arg, EXIT_UNKNOWN_ARGUMENT));
        }
        // A single leading '-' (e.g. macOS's `-psn_0_123...`) or a bare non-flag arg: ignored.
    }
    Ok(Args::Gui)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(args: &[&str]) -> Vec<String> {
        args.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn smoke_test_with_a_path() {
        assert_eq!(
            parse(v(&["--smoke-test", "x.json"])).unwrap(),
            Args::SmokeTest(PathBuf::from("x.json"))
        );
    }

    #[test]
    fn an_unknown_flag_exits_2() {
        let err = parse(v(&["--bogus"])).unwrap_err();
        assert_eq!(err.1, EXIT_UNKNOWN_ARGUMENT);
    }

    #[cfg(not(feature = "ci-hooks"))]
    #[test]
    fn ci_update_without_the_feature_exits_2() {
        let err = parse(v(&["--ci-update", "x.json"])).unwrap_err();
        assert_eq!(err.1, EXIT_UNKNOWN_ARGUMENT);
    }

    #[cfg(feature = "ci-hooks")]
    #[test]
    fn ci_update_with_the_feature_parses() {
        assert_eq!(
            parse(v(&["--ci-update", "x.json"])).unwrap(),
            Args::CiUpdate(PathBuf::from("x.json"))
        );
    }

    #[test]
    fn a_macos_psn_argument_is_ignored() {
        assert_eq!(parse(v(&["-psn_0_123456"])).unwrap(), Args::Gui);
    }

    #[test]
    fn no_arguments_is_gui() {
        assert_eq!(parse(v(&[])).unwrap(), Args::Gui);
    }
}
