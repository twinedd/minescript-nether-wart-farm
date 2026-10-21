# Nether Wart Farm for Minecraft 1.21.11

Automates nether wart harvesting and replanting with **Minescript + Baritone**.
It finds nearby farm floors, waits until 85% of a floor is mature, and puts
extra wart in chests. It does **not** sell items or log in to servers.

## Install

1. Install [Fabric Loader](https://fabricmc.net/use/?version=1.21.11) for
   Minecraft Java **1.21.11**. Use Java 21.
2. Put the 1.21.11 Fabric versions of [Fabric API](https://modrinth.com/mod/fabric-api),
   [Minescript 5.x](https://minescript.net/downloads/), and this repository's
   [`baritone-fabric-1.21.11-netherwart.jar`](mods/baritone-fabric-1.21.11-netherwart.jar)
   in your Minecraft instance's `mods` folder. Remove any other Baritone JAR
   from that folder.
3. Install Python 3. Copy the **files inside** this repository's `minescript`
   folder into the instance's `minescript` folder. Start Minecraft and run
   `\install_mappings` once in chat.

The instance folder is usually `.minecraft`. With some TLauncher profiles it
is `%APPDATA%\.tlauncher\legacy\Minecraft\game`. Use the folder of the
profile you actually launch.

## Use

Place accessible chests near the farm. Keep one nether wart for planting and
at least ten inventory slots free. Stand near your farm, then use these
commands in Minecraft chat:

| Command | Action |
| --- | --- |
| `\farm_probe` | Check detected floors and nearby chest candidates without harvesting. |
| `\start` | Choose chests, then keep harvesting, replanting, and storing wart. |
| `\start once` | Choose chests, run one harvest cycle, then stop. |
| `\farm_done` | Finish choosing chests and begin farming. |
| `\farm_status` | Show the latest status. |
| `\stop` | Stop the script and Baritone. |

Run `\farm_probe` first. Then enter `\start`, **right-click each chest** you
want the bot to use, close the chest menu between clicks, stand near the
center of the farm, and enter `\farm_done`. A double chest only needs one
click. `\stop` cancels chest selection or farming.

If the probe misses a floor, move closer to the farm's center and make sure
the area is loaded. A farm needs at least one planted wart to be detected.
The script keeps one wart stack for replanting, uses another selected chest
if the first is full, and stops if it cannot store the harvest.

You can change the 85% threshold and scan distances in `farm_config.json`.
For errors, check `farm.log` in the game's `minescript` folder. Minecraft must
stay open; join servers and complete their login steps yourself. The modified
Baritone JAR was tested on Fabric 1.21.11, while this public chest-only script
has automated tests but has not been tested on other servers.

The modified Baritone source and build notes are in
[BARITONE_CHANGES.md](BARITONE_CHANGES.md). The Minescript scripts are MIT
licensed; Baritone retains its LGPL-3.0 license.

## Кратко по-русски

Установите Fabric 1.21.11, Fabric API, Minescript, Python 3 и JAR Baritone из
репозитория. Файлы из `minescript/` положите в папку скриптов игры. В чате
выполните `\install_mappings`, затем `\farm_probe` и `\start`. Кликните ПКМ
по нужным сундукам, закрывая их меню, встаньте у центра фермы и введите
`\farm_done`. Бот собирает и сажает нарост, излишки кладёт в выбранные сундуки.
Остановка — `\stop`; продажи и автоматического входа нет.
