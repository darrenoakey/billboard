// PlaylistArtwork — applies queued cover images to Music.app library playlists.
//
// The Apple Music REST API has no endpoint for playlist artwork, so this helper is
// the one place billboard drives Music.app (via ScriptingBridge Apple Events, not
// AppleScript). It runs as its own signed .app bundle so macOS asks once for
// "PlaylistArtwork wants to control Music" and remembers the answer.
//
// Jobs: ~/.config/billboard/artwork_jobs/*.json  {"playlist_name": ..., "image_path": ...}
// Done: moved to artwork_jobs/done/ with a "result" field. Status: artwork_jobs/status.json
import AppKit
import Foundation
import ScriptingBridge

let jobsDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/billboard/artwork_jobs")
let doneDir = jobsDir.appendingPathComponent("done")
let statusFile = jobsDir.appendingPathComponent("status.json")
let retrySeconds: TimeInterval = 60
let giveUpSeconds: TimeInterval = 6 * 3600

func log(_ s: String) {
    let line = "\(ISO8601DateFormatter().string(from: Date())) \(s)\n"
    FileHandle.standardError.write(line.data(using: .utf8)!)
    let logURL = jobsDir.appendingPathComponent("helper.log")
    if let h = try? FileHandle(forWritingTo: logURL) { h.seekToEndOfFile(); h.write(line.data(using: .utf8)!); try? h.close() }
    else { try? line.write(to: logURL, atomically: true, encoding: .utf8) }
}

func writeStatus(_ status: [String: Any]) {
    var s = status
    s["updated"] = ISO8601DateFormatter().string(from: Date())
    if let d = try? JSONSerialization.data(withJSONObject: s, options: [.prettyPrinted, .sortedKeys]) { try? d.write(to: statusFile) }
}

enum Outcome { case applied, notYetSynced, permissionDenied(String), failed(String) }

func libraryPlaylists(_ music: SBApplication, named name: String) -> [SBObject] {
    guard let sources = music.value(forKey: "sources") as? SBElementArray, sources.count > 0,
          let library = sources.object(at: 0) as? SBObject,
          let playlists = library.value(forKey: "userPlaylists") as? SBElementArray else { return [] }
    guard let hits = playlists.filtered(using: NSPredicate(format: "name == %@", name)) as? SBElementArray else { return [] }
    return (0..<hits.count).compactMap { hits.object(at: $0) as? SBObject }
}

func apply(_ music: SBApplication, playlistName: String, imagePath: String) -> Outcome {
    guard let image = NSImage(contentsOfFile: imagePath) else { return .failed("cannot read image \(imagePath)") }
    let playlists = libraryPlaylists(music, named: playlistName)
    if playlists.isEmpty {
        if let err = music.lastError() as NSError?, err.code == -1743 { return .permissionDenied("Music automation not permitted (-1743)") }
        return .notYetSynced
    }
    for playlist in playlists {   // same-named duplicates all get the cover
        guard let artworks = playlist.value(forKey: "artworks") as? SBElementArray,
              let artwork = artworks.object(at: 0) as? SBObject else { return .failed("no artwork reference") }
        artwork.setValue(image, forKey: "data")
        if let err = music.lastError() as NSError? {
            if err.code == -1743 { return .permissionDenied("Music automation not permitted (-1743)") }
            return .failed("set artwork: \(err)")
        }
        if ((playlist.value(forKey: "artworks") as? SBElementArray)?.count ?? 0) == 0 { return .failed("artwork not present after set") }
    }
    return .applied
}

func pendingJobs() -> [(URL, [String: Any])] {
    let files = (try? FileManager.default.contentsOfDirectory(at: jobsDir, includingPropertiesForKeys: nil)) ?? []
    return files.filter { $0.pathExtension == "json" && $0.lastPathComponent != "status.json" }.sorted { $0.path < $1.path }
        .compactMap { url in
            guard let d = try? Data(contentsOf: url), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
            return (url, j)
        }
}

func finish(_ url: URL, _ job: [String: Any], result: String) {
    var j = job
    j["result"] = result
    j["finished"] = ISO8601DateFormatter().string(from: Date())
    try? FileManager.default.createDirectory(at: doneDir, withIntermediateDirectories: true)
    if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
        try? d.write(to: doneDir.appendingPathComponent(url.lastPathComponent))
    }
    try? FileManager.default.removeItem(at: url)
}

try? FileManager.default.createDirectory(at: jobsDir, withIntermediateDirectories: true)
guard let music = SBApplication(bundleIdentifier: "com.apple.Music") else { log("Music.app not found"); exit(1) }
music.timeout = 6 * 3600 * 60   // ticks; lets a pending permission prompt wait for the user
let started = Date()
log("started; pending jobs: \(pendingJobs().count)")
while true {
    let jobs = pendingJobs()
    if jobs.isEmpty { writeStatus(["state": "idle", "pending": 0]); log("no pending jobs"); break }
    var denied: String?
    var waiting: [String] = []
    for (url, job) in jobs {
        let name = job["playlist_name"] as? String ?? "", path = job["image_path"] as? String ?? ""
        switch apply(music, playlistName: name, imagePath: path) {
        case .applied: log("applied artwork to \(name)"); finish(url, job, result: "applied")
        case .notYetSynced: log("playlist not in Music.app yet: \(name)"); waiting.append(name)
        case .permissionDenied(let m): log(m); denied = m
        case .failed(let m): log("failed \(name): \(m)"); finish(url, job, result: "failed: \(m)")
        }
        if denied != nil { break }
    }
    if let m = denied {
        writeStatus(["state": "permission_denied", "detail": m, "pending": pendingJobs().count,
                     "fix": "System Settings > Privacy & Security > Automation > PlaylistArtwork > enable Music, then run ./run movie-artwork"])
        exit(2)
    }
    if waiting.isEmpty { continue }
    writeStatus(["state": "waiting_for_sync", "pending": waiting])
    if Date().timeIntervalSince(started) > giveUpSeconds { log("gave up waiting for sync"); exit(3) }
    Thread.sleep(forTimeInterval: retrySeconds)
}
