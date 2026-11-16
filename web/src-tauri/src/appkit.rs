//! macOS: route the system's quit requests through the shell, and round the
//! corners of the borderless window (the UI draws its own title bar).
//!
//! `quit app "ARGOS"`, the Dock's Quit and a log-out send the application
//! `terminate:`. tao 0.37 implements no `applicationShouldTerminate:` (its
//! `applicationWillTerminate:` exits at once), so such a quit could neither
//! show the Quit dialog (A7) nor be refused while a sequence runs. This adds
//! the method to tao's delegate class through the Objective-C runtime (no
//! crate: owner decision W8) and asks the shell: when the UI decides, the
//! request becomes the UI's Quit dialog and `terminate:` is cancelled; the
//! shell later ends the app itself. Otherwise the terminate goes ahead (the
//! `RunEvent::Exit` path stops the server).

use std::ffi::{c_char, c_void};
use std::sync::OnceLock;

type Id = *mut c_void;
type Sel = *mut c_void;

/// NSApplicationTerminateReply.
const TERMINATE_CANCEL: usize = 0;
const TERMINATE_NOW: usize = 1;

/// Decides a `terminate:`: true lets it go ahead, false cancels it.
type Decide = Box<dyn Fn() -> bool + Send + Sync>;
static DECIDE: OnceLock<Decide> = OnceLock::new();

#[link(name = "objc", kind = "dylib")]
extern "C" {
    fn objc_getClass(name: *const c_char) -> Id;
    fn sel_registerName(name: *const c_char) -> Sel;
    fn class_addMethod(class: Id, name: Sel, imp: *const c_void, types: *const c_char) -> bool;
    fn objc_msgSend();
}

extern "C" fn should_terminate(_this: Id, _cmd: Sel, _sender: Id) -> usize {
    match DECIDE.get() {
        Some(decide) if !decide() => TERMINATE_CANCEL,
        _ => TERMINATE_NOW,
    }
}

/// Install the hook. Main thread, after the event loop exists (Tauri's
/// `setup`). Returns false when tao's delegate class is missing or already
/// answers `applicationShouldTerminate:` (a newer tao: check its behaviour).
pub fn route_terminate(decide: impl Fn() -> bool + Send + Sync + 'static) -> bool {
    if DECIDE.set(Box::new(decide)).is_err() {
        return false;
    }
    // SAFETY: plain Objective-C runtime calls on the main thread; the method
    // signature matches `- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)`
    // (type encoding "Q@:@": NSUInteger return, self, _cmd, one object).
    unsafe {
        let class = objc_getClass(c"TaoAppDelegateParent".as_ptr());
        if class.is_null() {
            return false;
        }
        let selector = sel_registerName(c"applicationShouldTerminate:".as_ptr());
        let imp = should_terminate as extern "C" fn(Id, Sel, Id) -> usize as *const c_void;
        if !class_addMethod(class, selector, imp, c"Q@:@".as_ptr()) {
            return false;
        }
        // NSApplication caches which optional methods its delegate answers
        // when the delegate is set: set it again so the new one is seen.
        let send0: extern "C" fn(Id, Sel) -> Id = std::mem::transmute(objc_msgSend as *const ());
        let send1: extern "C" fn(Id, Sel, Id) = std::mem::transmute(objc_msgSend as *const ());
        let app = send0(
            objc_getClass(c"NSApplication".as_ptr()),
            sel_registerName(c"sharedApplication".as_ptr()),
        );
        let delegate = send0(app, sel_registerName(c"delegate".as_ptr()));
        if app.is_null() || delegate.is_null() {
            return false;
        }
        let set_delegate = sel_registerName(c"setDelegate:".as_ptr());
        send1(app, set_delegate, std::ptr::null_mut());
        send1(app, set_delegate, delegate);
    }
    true
}

/// The corner radius of a macOS window (11 to 15; points).
pub const CORNER_RADIUS: f64 = 10.0;

/// Round the corners of the borderless window `ns_window` (an `NSWindow *`):
/// the window is made non-opaque on a clear background, its content view
/// layer-backed with `radius` and clipped to it, and its shadow recomputed
/// from that shape. A titled window would round itself, but macOS then draws
/// a grey outline around it that no theme can colour (Night Red, BRAND 4.3,
/// design review W8); the borderless window keeps every pixel the UI's. `0`
/// squares it again (full screen). Main thread only.
pub fn round_corners(ns_window: *mut c_void, radius: f64) -> bool {
    if ns_window.is_null() {
        return false;
    }
    // SAFETY: plain Objective-C messages on the main thread to a live window
    // and its content view: `setOpaque:` / `setWantsLayer:` /
    // `setMasksToBounds:` take a BOOL (one byte), `setBackgroundColor:` an
    // object, `setCornerRadius:` a CGFloat (f64); `contentView`, `layer` and
    // `+[NSColor clearColor]` return objects; `invalidateShadow` takes nothing.
    unsafe {
        let get: extern "C" fn(Id, Sel) -> Id = std::mem::transmute(objc_msgSend as *const ());
        let set_flag: extern "C" fn(Id, Sel, bool) = std::mem::transmute(objc_msgSend as *const ());
        let set_object: extern "C" fn(Id, Sel, Id) = std::mem::transmute(objc_msgSend as *const ());
        let set_float: extern "C" fn(Id, Sel, f64) = std::mem::transmute(objc_msgSend as *const ());
        let send: extern "C" fn(Id, Sel) = std::mem::transmute(objc_msgSend as *const ());
        let sel = |name: &std::ffi::CStr| sel_registerName(name.as_ptr());
        let clear = get(objc_getClass(c"NSColor".as_ptr()), sel(c"clearColor"));
        set_flag(ns_window, sel(c"setOpaque:"), false);
        set_object(ns_window, sel(c"setBackgroundColor:"), clear);
        let content = get(ns_window, sel(c"contentView"));
        if content.is_null() {
            return false;
        }
        set_flag(content, sel(c"setWantsLayer:"), true);
        let layer = get(content, sel(c"layer"));
        if layer.is_null() {
            return false;
        }
        set_float(layer, sel(c"setCornerRadius:"), radius);
        set_flag(layer, sel(c"setMasksToBounds:"), true);
        send(ns_window, sel(c"invalidateShadow"));
    }
    true
}
