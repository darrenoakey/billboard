// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MusicTokenApp",
    platforms: [
        .macOS(.v12)
    ],
    targets: [
        .executableTarget(
            name: "MusicTokenApp",
            dependencies: [],
            path: "Sources"
        )
    ]
)
