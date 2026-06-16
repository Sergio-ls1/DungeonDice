@echo off
echo Building Dungeon Dice executable...
pyinstaller --paths dungeon_dice --onefile --windowed --name DungeonDice --add-data "assets;assets" --add-data "config;config" --add-data "saves;saves" --add-data "tiny-RPG-forest-files;tiny-RPG-forest-files" --add-data "Tiny RPG Mountain Files;Tiny RPG Mountain Files" dungeon_dice/game.py
echo Build process complete.
