# Modified Baritone

The `baritone/` directory contains the corresponding source for the modified
`mods/baritone-fabric-1.21.11-netherwart.jar`. It starts from upstream
[`cabaletta/baritone`](https://github.com/cabaletta/baritone) commit
`23723891da460ef15797b02fe5b385b0c5b163cc` on the 1.21.11 branch.

Changes in `baritone/src/api/java/baritone/api/Settings.java` and
`baritone/src/main/java/baritone/process/FarmProcess.java` add:

- `#replantNetherWart true` — replant empty soul-sand cells.
- `#farmUsingSelection true` — restrict the farm process to the selected plot.
- `#harvestImmatureNetherWart true` — an optional manual test setting. The
  controller forces it to `false` during normal use and on shutdown.
- Farm behavior adjustments for nether wart on soul sand.

The binary was built with the upstream Gradle wrapper for Minecraft 1.21.11
and is byte-for-byte identical to the locally tested Baritone jar (SHA-256
`19ef1791910f1f53747db5cf6bd85c8b7a655a1791c2e0a2a49b26ab414d10e9`).
Baritone's original license and notices are preserved in `baritone/LICENSE`
and its source tree. The Minescript controller has its own MIT license in
`minescript/LICENSE`.

To rebuild the Fabric jar, use Java 21 and run the upstream Gradle wrapper in
`baritone/`:

```powershell
.\gradlew.bat :fabric:remapJar --no-daemon --configure-on-demand
```

Gradle places the distributable jar in `baritone/fabric/build/libs/`.
