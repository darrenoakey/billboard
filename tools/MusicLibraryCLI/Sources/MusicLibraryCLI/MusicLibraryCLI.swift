import Foundation
import MusicKit

@main
struct MusicLibraryCLI {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count >= 2 else {
            printUsage()
            exit(1)
        }

        switch args[1] {
        case "list-playlists":
            await listPlaylists()
        default:
            printUsage()
            exit(1)
        }
    }

    static func printUsage() {
        print("""
        Usage: music-library-cli <command>

        Commands:
          list-playlists    List library playlists as JSON
        """)
    }

    static func listPlaylists() async {
        let status = await MusicAuthorization.request()
        guard status == .authorized else {
            print("{\"error\":\"not_authorized\",\"status\":\"\\(status)\"}")
            exit(1)
        }

        do {
            var playlists: [Playlist] = []
            let limit = 100
            var offset = 0
            while true {
                var request = MusicLibraryRequest<Playlist>()
                request.limit = limit
                request.offset = offset
                let response = try await request.response()
                playlists.append(contentsOf: response.items)
                if response.items.count < limit {
                    break
                }
                offset += response.items.count
            }

            let output = playlists.map { playlist -> [String: String] in
                let id = playlist.id.rawValue
                return [
                    "id": id,
                    "name": playlist.name,
                ]
            }

            let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted])
            if let json = String(data: data, encoding: .utf8) {
                print(json)
            } else {
                print("{\"error\":\"json_encode_failed\"}")
                exit(1)
            }
        } catch {
            let message = String(describing: error)
            let escaped = message.replacingOccurrences(of: "\"", with: "\\\"")
            print("{\"error\":\"request_failed\",\"message\":\"\(escaped)\"}")
            exit(1)
        }
    }
}
