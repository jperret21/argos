//! The shell's own two pages, served on the `argos:` scheme: the start-up
//! failure and "Starting the ARGOS server…" after its Retry.
//!
//! A fallback only. The web UI shows the start-up stages, the start-up
//! failure and the crash notice itself, in the observer's theme
//! (`argos://server-state`, main.rs); these pages appear when no UI has
//! attached (it did not load, or predates the bridge). They use the
//! Observatory tokens of web/src/design/tokens.css, or its Night Red ones
//! when the UI last said Night Red (`argos://theme`; BRAND 4.3: no grey or
//! gold pixel at the telescope), and the generator's mark
//! (web/src/design/brand/argos-mark.svg, included as is, never redrawn). The
//! window has no system title bar (Q-G14): a strip along the top drags it,
//! and the failure page has its own Quit.

/// The ARGOS mark, `currentColor` strokes (generator output).
const MARK_SVG: &str = include_str!("../../src/design/brand/argos-mark.svg");

/// What the failure page shows.
#[derive(Clone)]
pub struct Failure {
    /// "ARGOS could not start", or "The ARGOS server stopped" after start-up.
    pub title: &'static str,
    pub cause: String,
    pub details: String,
    pub log_dir: String,
    /// How the process ended ("exit status 1", "signal 9"), when it did.
    pub status: Option<String>,
}

fn escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

const STYLE: &str = r#"
:root { color-scheme: dark; --bg: #191b1f; --bg-2: #121417; --fg: #e8e5df;
  --fg-muted: #aaa8a2; --border: #47515c; --accent: #c49a3c; --danger: #bf7772; }
:root[data-theme="night-red"] { --bg: #1a0304; --bg-2: #100102; --fg: #d88f8f;
  --fg-muted: #a65758; --border: #501719; --accent: #c14d50; --danger: #e05e61; }
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
  font: 14px/1.45 "IBM Plex Sans", -apple-system, system-ui, sans-serif; }
body { display: grid; place-items: center; padding: 24px; }
main { width: min(720px, 100%); display: flex; flex-direction: column; align-items: center; gap: 12px; }
.mark { width: 96px; height: 96px; color: var(--accent); }
.mark svg { width: 100%; height: 100%; display: block; }
.word { font-weight: 600; letter-spacing: 0.04em; font-size: 22px; }
.muted { color: var(--fg-muted); }
.bar { width: 280px; height: 3px; background: var(--bg-2); border-radius: 2px; overflow: hidden; }
.bar i { display: block; width: 30%; height: 100%; background: var(--fg-muted);
  animation: slide 1.4s ease-in-out infinite alternate; }
@keyframes slide { from { transform: translateX(-10%); } to { transform: translateX(245%); } }
@media (prefers-reduced-motion: reduce) { .bar i { animation: none; width: 100%; opacity: .5; } }
footer { position: fixed; bottom: 16px; left: 0; right: 0; text-align: center; font-size: 12px; }
.fail { align-items: stretch; }
.fail h1 { font-size: 18px; margin: 0; font-weight: 600; }
.fail .cause { margin: 0; }
.fail .cause::before { content: ""; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; border: 2px solid var(--danger); margin-right: 8px; vertical-align: 1px; }
pre { margin: 0; max-height: 46vh; overflow: auto; padding: 10px 12px; background: var(--bg-2);
  border: 1px solid var(--border); border-radius: 4px; color: var(--fg);
  font: 12px/1.5 "IBM Plex Mono", ui-monospace, Menlo, monospace; white-space: pre;
  user-select: text; }
.row { display: flex; gap: 8px; align-items: center; }
.row .grow { flex: 1; }
button { font: inherit; color: var(--fg); background: transparent; border: 1px solid var(--border);
  border-radius: 4px; padding: 5px 12px; cursor: pointer; }
button:hover { border-color: var(--fg-muted); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
::selection { background: var(--border); color: var(--fg); }
.drag { position: fixed; top: 0; left: 0; right: 0; height: 32px; }
"#;

/// The pages' policy: inline style and script only, the `argos:` scheme for
/// Retry / Quit, and Tauri's IPC for the drag strip.
pub const CSP: &str = "default-src 'none'; style-src 'unsafe-inline'; \
script-src 'unsafe-inline'; connect-src 'self' ipc: http://ipc.localhost";

fn page(title: &str, body: &str, script: &str, night_red: bool) -> String {
    let theme = if night_red {
        " data-theme=\"night-red\""
    } else {
        ""
    };
    format!(
        "<!doctype html><html lang=\"en\"{theme}><head><meta charset=\"utf-8\">\
<meta name=\"color-scheme\" content=\"dark\"><title>{title}</title>\
<style>{STYLE}</style></head><body>\
<div class=\"drag\" data-tauri-drag-region></div>{body}<script>{script}</script></body></html>"
    )
}

/// "Starting the ARGOS server…", with the seconds spent so far.
pub fn starting(version: &str, night_red: bool) -> String {
    let body = format!(
        "<main><div class=\"mark\" aria-hidden=\"true\">{MARK_SVG}</div>\
<div class=\"word\">ARGOS</div><div class=\"muted\">Version {version}</div>\
<div class=\"bar\" role=\"progressbar\" aria-label=\"Starting\"><i></i></div>\
<div role=\"status\">Starting the ARGOS server&hellip; <span class=\"muted\" id=\"t\"></span></div>\
</main><footer class=\"muted\">GNU GPL v3 or later &middot; free software with no warranty</footer>",
        version = escape(version)
    );
    let script = "const t0=Date.now();setInterval(()=>{const s=Math.round((Date.now()-t0)/1000);\
document.getElementById('t').textContent=s>=2?s+' s':'';},500);";
    page("ARGOS", &body, script, night_red)
}

/// The start-up failure: cause, the server's last stderr lines, log folder,
/// Copy details, Open log folder, Quit, Retry.
pub fn failure(version: &str, failure: &Failure, night_red: bool) -> String {
    let details = if failure.details.trim().is_empty() {
        "(the server wrote nothing on stderr)".to_owned()
    } else {
        failure.details.clone()
    };
    let body = format!(
        "<main class=\"fail\"><h1>{title}</h1>\
<p class=\"cause\" role=\"alert\">{cause}</p>\
<pre id=\"d\" tabindex=\"0\">{details}</pre>\
<div class=\"muted\" id=\"log\">Log folder: {log_dir}</div>\
<div class=\"row\"><button id=\"copy\">Copy details</button>\
<button id=\"open\">Open log folder</button><span class=\"grow\"></span>\
<button id=\"quit\">Quit</button><button id=\"retry\">Retry</button></div>\
<div class=\"muted\">ARGOS {version}</div></main>",
        title = escape(failure.title),
        cause = escape(&failure.cause),
        details = escape(&details),
        log_dir = escape(&failure.log_dir),
        version = escape(version),
    );
    let script = "const $=id=>document.getElementById(id);\
$('copy').onclick=()=>{const a=document.createElement('textarea');\
a.value=document.querySelector('.cause').textContent+'\\n\\n'+$('d').textContent+'\\n\\n'+$('log').textContent;\
document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();\
$('copy').textContent='Copied';setTimeout(()=>{$('copy').textContent='Copy details'},1500);};\
$('open').onclick=()=>fetch('/open-log-folder',{method:'POST'});\
$('quit').onclick=()=>{$('quit').disabled=true;fetch('/quit',{method:'POST'});};\
$('retry').onclick=()=>{$('retry').disabled=true;\
fetch('/retry',{method:'POST'}).finally(()=>location.replace('/'));};\
$('d').scrollTop=$('d').scrollHeight;$('retry').focus();";
    page(failure.title, &body, script, night_red)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escapes_markup() {
        assert_eq!(
            escape("<a href=\"x\">'&'</a>"),
            "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;"
        );
    }

    #[test]
    fn starting_page_carries_the_mark_and_the_stage() {
        let html = starting("0.4.2", false);
        assert!(
            html.contains("stroke=\"currentColor\""),
            "the generator's mark, inline"
        );
        assert!(html.contains("Starting the ARGOS server"));
        assert!(html.contains("Version 0.4.2"));
        assert!(
            !html.contains("src=") && !html.contains("href="),
            "no resource to load"
        );
        assert!(
            html.contains("data-tauri-drag-region"),
            "no title bar: a drag strip"
        );
        assert!(
            html.contains("<html lang=\"en\"><head>"),
            "Observatory by default"
        );
        assert!(
            starting("0.4.2", true).contains("<html lang=\"en\" data-theme=\"night-red\">"),
            "Night Red at the telescope"
        );
    }

    #[test]
    fn failure_page_escapes_the_server_output() {
        let failure = Failure {
            title: "ARGOS could not start",
            cause: "The ARGOS server stopped during start-up (exit status 2).".into(),
            details: "error: <script>alert(1)</script>".into(),
            log_dir: "/tmp/logs".into(),
            status: Some("exit status 2".into()),
        };
        let html = failure_page(&failure);
        assert!(html.contains("&lt;script&gt;alert(1)&lt;/script&gt;"));
        assert!(!html.contains("<script>alert"));
        assert!(html.contains("exit status 2"));
        assert!(html.contains("<h1>ARGOS could not start</h1>"));
        assert!(html.contains("Log folder: /tmp/logs"));
        let empty = Failure {
            details: " \n".into(),
            ..failure
        };
        assert!(failure_page(&empty).contains("the server wrote nothing on stderr"));
        assert!(
            failure_page(&empty).contains("id=\"quit\""),
            "a way out without a title bar"
        );
    }

    fn failure_page(failure: &Failure) -> String {
        super::failure("0.4.2", failure, false)
    }
}
