import Foundation
import StoreKit
import AppKit

class AppDelegate: NSObject, NSApplicationDelegate {
    var developerToken: String?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments

        if args.count >= 2 {
            developerToken = args[1]
            requestUserToken()
        } else {
            print("Usage: MusicTokenGetter <developer_token>")
            NSApplication.shared.terminate(nil)
        }
    }

    func requestUserToken() {
        guard let devToken = developerToken else {
            print("ERROR: No developer token")
            NSApplication.shared.terminate(nil)
            return
        }

        SKCloudServiceController.requestAuthorization { status in
            switch status {
            case .authorized:
                self.fetchUserToken(developerToken: devToken)
            case .denied:
                print("ERROR: Authorization denied")
                NSApplication.shared.terminate(nil)
            case .notDetermined:
                print("ERROR: Authorization not determined")
                NSApplication.shared.terminate(nil)
            case .restricted:
                print("ERROR: Authorization restricted")
                NSApplication.shared.terminate(nil)
            @unknown default:
                print("ERROR: Unknown authorization status")
                NSApplication.shared.terminate(nil)
            }
        }
    }

    func fetchUserToken(developerToken: String) {
        let controller = SKCloudServiceController()
        controller.requestUserToken(forDeveloperToken: developerToken) { token, error in
            if let error = error {
                print("ERROR: \(error.localizedDescription)")
                NSApplication.shared.terminate(nil)
                return
            }

            if let token = token {
                print("USER_TOKEN:\(token)")

                let homeDir = FileManager.default.homeDirectoryForCurrentUser
                let configDir = homeDir.appendingPathComponent(".config/billboard")
                try? FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
                let tokenFile = configDir.appendingPathComponent("music_user_token")
                try? token.write(to: tokenFile, atomically: true, encoding: .utf8)
                print("SAVED:\(tokenFile.path)")
            } else {
                print("ERROR: No token returned")
            }

            NSApplication.shared.terminate(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
