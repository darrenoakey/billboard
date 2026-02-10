// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MusicHelper",
    platforms: [
        .macOS(.v12)
    ],
    targets: [
        .executableTarget(
            name: "music-helper",
            dependencies: [],
            path: "Sources"
        )
    ]
)
