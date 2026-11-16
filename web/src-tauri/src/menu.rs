//! The native macOS menu bar (Q-G10): App, File, Edit, View, Window, Help,
//! mirroring the in-window commands and adding no function of its own. Linux
//! gets no menu bar: the window has a custom title bar (Q-G14) and the UI's
//! own Help menu.
//!
//! Every custom item but Quit reaches the UI as `argos://menu {id}`, `id`
//! one of the UI's command ids (web/src/lib/shell/desktop/bridge.ts
//! `MENU_COMMANDS`, the keymap's ids where a key exists); the accelerators
//! shown are the UI's own keys, which the page handles first. Quit is the
//! shell's quit request (main.rs), never a bare `terminate:`. The Edit items
//! are needed by WKWebView for ⌘C / ⌘V in text fields.

use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Wry};

/// Quit: handled by the shell, not forwarded.
pub const QUIT: &str = "app.quit";

/// The forwarded items: (id, label, accelerator), by menu.
const APP: [(&str, &str, Option<&str>); 2] = [
    ("help.about", "About {product}", None),
    ("nav.settings.mod", "Settings…", Some("CmdOrCtrl+,")),
];
const FILE: [(&str, &str, Option<&str>); 2] = [
    ("file.open-fits", "Open FITS Image…", Some("CmdOrCtrl+O")),
    (
        "review.sessions",
        "Open Session…",
        Some("CmdOrCtrl+Shift+O"),
    ),
];
const VIEW_SECTIONS: [(&str, &str, Option<&str>); 5] = [
    ("nav.connection", "Connection", Some("CmdOrCtrl+1")),
    ("nav.observe", "Observe", Some("CmdOrCtrl+2")),
    ("nav.plan", "Plan", Some("CmdOrCtrl+3")),
    ("nav.review", "Review", Some("CmdOrCtrl+4")),
    ("nav.settings", "Settings", Some("CmdOrCtrl+5")),
];
const VIEW_TOOLS: [(&str, &str, Option<&str>); 3] = [
    ("log.toggle", "Activity Log", None),
    ("palette.open", "Command Palette…", Some("CmdOrCtrl+K")),
    ("theme.cycle", "Next Theme", None),
];
const VIEW_RESET: (&str, &str, Option<&str>) = ("layout.reset-all", "Reset All Layouts", None);
const HELP: [(&str, &str, Option<&str>); 3] = [
    ("help.shortcuts", "Keyboard Shortcuts", None),
    // "&&": a single "&" would be read as a mnemonic (Qt P11).
    ("help.docs", "Documentation && Website", None),
    ("help.bundle", "Create Support Bundle…", None),
];

/// Every forwarded id (the UI's MENU_COMMANDS minus app.quit).
pub fn forwarded() -> impl Iterator<Item = &'static str> {
    APP.iter()
        .chain(&FILE)
        .chain(&VIEW_SECTIONS)
        .chain(&VIEW_TOOLS)
        .chain(std::iter::once(&VIEW_RESET))
        .chain(&HELP)
        .map(|(id, _, _)| *id)
}

pub fn build(app: &AppHandle, product: &str) -> tauri::Result<Menu<Wry>> {
    let item = |(id, text, accelerator): (&str, &str, Option<&str>)| {
        MenuItem::with_id(
            app,
            id,
            text.replace("{product}", product),
            true,
            accelerator,
        )
    };
    let items = |list: &[(&'static str, &'static str, Option<&'static str>)]| {
        list.iter()
            .map(|entry| item(*entry))
            .collect::<tauri::Result<Vec<_>>>()
    };
    let sep = || PredefinedMenuItem::separator(app);
    let refs = |list: &[MenuItem<Wry>]| -> Vec<Box<dyn IsMenuItem<Wry>>> {
        list.iter()
            .map(|i| Box::new(i.clone()) as Box<dyn IsMenuItem<Wry>>)
            .collect()
    };
    let submenu = |title: &str, entries: Vec<Box<dyn IsMenuItem<Wry>>>| {
        let borrowed: Vec<&dyn IsMenuItem<Wry>> = entries.iter().map(|e| e.as_ref()).collect();
        Submenu::with_items(app, title, true, &borrowed)
    };
    let boxed = |i: PredefinedMenuItem<Wry>| Box::new(i) as Box<dyn IsMenuItem<Wry>>;

    let app_items = items(&APP)?;
    let mut entries = refs(&app_items[..1]);
    entries.push(boxed(sep()?));
    entries.extend(refs(&app_items[1..]));
    entries.push(boxed(sep()?));
    entries.push(boxed(PredefinedMenuItem::hide(
        app,
        Some(&format!("Hide {product}")),
    )?));
    entries.push(boxed(PredefinedMenuItem::hide_others(app, None)?));
    entries.push(boxed(PredefinedMenuItem::show_all(app, None)?));
    entries.push(boxed(sep()?));
    entries.push(Box::new(item((
        QUIT,
        "Quit {product}",
        Some("CmdOrCtrl+Q"),
    ))?));
    let app_menu = submenu(product, entries)?;

    let file = submenu("File", refs(&items(&FILE)?))?;

    let edit = submenu(
        "Edit",
        vec![
            boxed(PredefinedMenuItem::undo(app, None)?),
            boxed(PredefinedMenuItem::redo(app, None)?),
            boxed(sep()?),
            boxed(PredefinedMenuItem::cut(app, None)?),
            boxed(PredefinedMenuItem::copy(app, None)?),
            boxed(PredefinedMenuItem::paste(app, None)?),
            boxed(PredefinedMenuItem::select_all(app, None)?),
        ],
    )?;

    let mut entries = refs(&items(&VIEW_SECTIONS)?);
    entries.push(boxed(sep()?));
    entries.extend(refs(&items(&VIEW_TOOLS)?));
    entries.push(boxed(sep()?));
    entries.push(Box::new(item(VIEW_RESET)?));
    let view = submenu("View", entries)?;

    let window = submenu(
        "Window",
        vec![
            boxed(PredefinedMenuItem::minimize(app, None)?),
            boxed(PredefinedMenuItem::maximize(app, Some("Zoom"))?),
            boxed(PredefinedMenuItem::fullscreen(app, None)?),
            boxed(sep()?),
            boxed(PredefinedMenuItem::bring_all_to_front(app, None)?),
        ],
    )?;

    let help_items = items(&HELP)?;
    let mut entries = refs(&help_items[..2]);
    entries.push(boxed(sep()?));
    entries.extend(refs(&help_items[2..]));
    let help = submenu("Help", entries)?;

    let menu = Menu::with_items(app, &[&app_menu, &file, &edit, &view, &window, &help])?;
    window.set_as_windows_menu_for_nsapp()?;
    help.set_as_help_menu_for_nsapp()?;
    Ok(menu)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The ids the UI accepts (web/src/lib/shell/desktop/bridge.ts MENU_COMMANDS).
    #[test]
    fn every_item_is_a_ui_command() {
        let bridge = include_str!("../../src/lib/shell/desktop/bridge.ts");
        let start = bridge
            .find("MENU_COMMANDS = [")
            .expect("MENU_COMMANDS in bridge.ts");
        let list = &bridge[start..start + bridge[start..].find(']').expect("end of list")];
        let mut ids: Vec<&str> = forwarded().collect();
        ids.push(QUIT);
        for id in &ids {
            assert!(
                list.contains(&format!("'{id}'")),
                "{id} is not in MENU_COMMANDS"
            );
        }
        let mut unique = ids.clone();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), ids.len(), "an id appears twice");
    }
}
