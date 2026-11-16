//! Tauri's build step, after one check: the shell's version (Cargo.toml,
//! which tauri.conf.json leaves unset and so follows) is the application's,
//! `__version__` in argos/__init__.py, the one source (owner decision W8).
//! A bump changes both; tests/packaging/test_desktop_shell.py checks the
//! same in the Python suite.

use std::path::Path;

fn main() {
    let init = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../argos/__init__.py");
    println!("cargo:rerun-if-changed={}", init.display());
    let text = std::fs::read_to_string(&init)
        .unwrap_or_else(|err| panic!("cannot read {}: {err}", init.display()));
    let argos = text
        .lines()
        .find_map(|line| line.strip_prefix("__version__ = \""))
        .and_then(|rest| rest.strip_suffix('"'))
        .unwrap_or_else(|| panic!("no __version__ = \"…\" line in {}", init.display()));
    let shell = env!("CARGO_PKG_VERSION");
    assert!(
        shell == argos,
        "web/src-tauri/Cargo.toml version {shell} differs from argos/__init__.py \
         __version__ {argos}: set Cargo.toml to {argos}"
    );
    tauri_build::build()
}
