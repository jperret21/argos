// WebKit probe for the ARGOS lab: loads a page in a real WKWebView (the
// engine Tauri v2 uses on macOS), optionally runs JavaScript, prints a JSON
// result and saves a PNG snapshot. No Safari automation setting needed.
//
// Build (Command Line Tools are enough):
//   swiftc -O web/lab/research/demos/webkit-probe.swift -o /tmp/webkit-probe
// WKWebView gates some features on the SDK the binary was linked with
// (e.g. the Popover API needs an app linked on the macOS 14+ SDK). To probe
// what a Tauri app built with a current Xcode gets, re-stamp the binary:
//   vtool -set-build-version macos 13.0 26.0 -replace -output /tmp/webkit-probe26 /tmp/webkit-probe
//   codesign -s - -f /tmp/webkit-probe26
//
// Usage:
//   webkit-probe <url> [--out shot.png] [--size 1440x900] [--wait ms]
//                [--eval "js returning a string or a Promise of one"]
//                [--before "js run after load, before the wait"]
//
// The window is on screen but fully transparent and click-through, behind
// every other window: an offscreen or hidden window gets its rendering and
// requestAnimationFrame throttled by WebKit, which would falsify timings.

import Cocoa
import WebKit

var url = ""
var out: String? = nil
var width = 1440.0
var height = 900.0
var waitMs = 1500.0
var evalJs: String? = nil
var beforeJs: String? = nil

var args = Array(CommandLine.arguments.dropFirst())
while !args.isEmpty {
  let a = args.removeFirst()
  switch a {
  case "--out": out = args.removeFirst()
  case "--size":
    let p = args.removeFirst().split(separator: "x").compactMap { Double($0) }
    if p.count == 2 { width = p[0]; height = p[1] }
  case "--wait": waitMs = Double(args.removeFirst()) ?? waitMs
  case "--eval": evalJs = args.removeFirst()
  case "--before": beforeJs = args.removeFirst()
  default: url = a
  }
}
if url.isEmpty {
  FileHandle.standardError.write("usage: webkit-probe <url> [--out f.png] [--size WxH] [--wait ms] [--eval js] [--before js]\n".data(using: .utf8)!)
  exit(2)
}

final class Probe: NSObject, WKNavigationDelegate, WKUIDelegate {
  let view: WKWebView
  init(_ v: WKWebView) { view = v }

  func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
    if let js = beforeJs {
      w.evaluateJavaScript(js) { _, _ in }
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + waitMs / 1000) { self.finish() }
  }

  func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { fail("navigation: \(e)") }
  func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { fail("load: \(e)") }

  func fail(_ m: String) {
    FileHandle.standardError.write("webkit-probe: \(m)\n".data(using: .utf8)!)
    exit(1)
  }

  func finish() {
    let next = { self.snapshot() }
    guard let js = evalJs else { next(); return }
    // callAsyncJavaScript awaits a returned Promise (macOS 11+).
    view.callAsyncJavaScript("return await (async () => { return (\(js)); })()", arguments: [:], in: nil, in: .page) { r in
      switch r {
      case .success(let v): print(v as? String ?? String(describing: v))
      case .failure(let e): print("{\"error\": \"\(e.localizedDescription)\"}")
      }
      next()
    }
  }

  func snapshot() {
    guard let path = out else { exit(0) }
    let cfg = WKSnapshotConfiguration()
    cfg.afterScreenUpdates = true
    view.takeSnapshot(with: cfg) { img, err in
      guard let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
            let png = rep.representation(using: .png, properties: [:]) else {
        self.fail("snapshot: \(String(describing: err))")
        return
      }
      do { try png.write(to: URL(fileURLWithPath: path)) } catch { self.fail("write: \(error)") }
      FileHandle.standardError.write("webkit-probe: saved \(path) (\(rep.pixelsWide)x\(rep.pixelsHigh) px)\n".data(using: .utf8)!)
      exit(0)
    }
  }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let screen = NSScreen.main?.frame ?? NSRect(x: 0, y: 0, width: width, height: height)
let win = NSWindow(contentRect: NSRect(x: screen.minX, y: screen.minY, width: width, height: height),
                   styleMask: [.borderless], backing: .buffered, defer: false)
win.alphaValue = 0.0
win.ignoresMouseEvents = true
win.level = NSWindow.Level(rawValue: NSWindow.Level.normal.rawValue - 1)
let conf = WKWebViewConfiguration()
// Private, test-only switches (guarded): a transparent window is "occluded",
// which would suspend requestAnimationFrame and throttle timers.
let prefs = conf.preferences
for key in ["hiddenPageDOMTimerThrottlingEnabled", "pageVisibilityBasedProcessSuppressionEnabled"] {
  if prefs.responds(to: NSSelectorFromString("_set" + key.prefix(1).uppercased() + key.dropFirst() + ":")) {
    prefs.setValue(false, forKey: key)
  }
}
let view = WKWebView(frame: NSRect(x: 0, y: 0, width: width, height: height), configuration: conf)
if view.responds(to: NSSelectorFromString("_setWindowOcclusionDetectionEnabled:")) {
  view.setValue(false, forKey: "windowOcclusionDetectionEnabled")
}
win.contentView = view
win.orderBack(nil)
let probe = Probe(view)
view.navigationDelegate = probe
view.uiDelegate = probe
view.load(URLRequest(url: URL(string: url)!))
DispatchQueue.main.asyncAfter(deadline: .now() + 120) { probe.fail("timeout") }
app.run()
