// Read-only in-process LaunchServices lookup; does not launch or control applications.
import AppKit
import Foundation
let samples = 1000
let identifiers = ["com.apple.Safari", "md.obsidian", "com.openai.codex"]
for identifier in identifiers {
    var timings = [Double](), found = 0
    for _ in 0..<samples {
        let start = DispatchTime.now().uptimeNanoseconds
        let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: identifier)
        timings.append(Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000.0)
        if url != nil { found += 1 }
    }
    timings.sort()
    print("\(identifier) n=\(samples) median_ms=\(String(format: "%.4f", (timings[499] + timings[500]) / 2)) p95_ms=\(String(format: "%.4f", timings[949])) found=\(found)")
}
