import Foundation
import StoreKit

// Music Helper CLI
// Gets Music User Token using StoreKit

@main
struct MusicHelper {
    static func main() {
        let args = CommandLine.arguments

        guard args.count >= 2 else {
            printUsage()
            exit(1)
        }

        let command = args[1]

        switch command {
        case "get-user-token":
            guard args.count >= 3 else {
                print("Usage: music-helper get-user-token <developer_token>")
                exit(1)
            }
            let developerToken = args[2]
            getUserToken(developerToken: developerToken)
        case "check-auth":
            checkAuthorization()
        default:
            printUsage()
            exit(1)
        }

        // Keep running for async callbacks
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 30))
    }

    static func printUsage() {
        print("""
        Usage: music-helper <command> [args]

        Commands:
          get-user-token <dev_token>    Get Music User Token
          check-auth                    Check authorization status
        """)
    }

    static func checkAuthorization() {
        SKCloudServiceController.requestAuthorization { status in
            switch status {
            case .authorized:
                print("STATUS: authorized")
            case .denied:
                print("STATUS: denied")
            case .notDetermined:
                print("STATUS: notDetermined")
            case .restricted:
                print("STATUS: restricted")
            @unknown default:
                print("STATUS: unknown")
            }
            exit(0)
        }
    }

    static func getUserToken(developerToken: String) {
        SKCloudServiceController.requestAuthorization { status in
            guard status == .authorized else {
                print("ERROR: Not authorized (status: \(status.rawValue))")
                exit(1)
            }

            let controller = SKCloudServiceController()
            controller.requestUserToken(forDeveloperToken: developerToken) { token, error in
                if let error = error {
                    print("ERROR: \(error.localizedDescription)")
                    exit(1)
                }

                if let token = token {
                    print("TOKEN: \(token)")
                    exit(0)
                } else {
                    print("ERROR: No token returned")
                    exit(1)
                }
            }
        }
    }
}
