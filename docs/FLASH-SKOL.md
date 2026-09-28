# Flash Pocket Alfred från valfri dator (skolan)

## Alternativ 1: Arduino IDE (mest klick)
1. Arduino IDE 2.x + "M5Stack" boards (Boards Manager: "M5Stack" → installera M5Core2-paketet)
2. Öppna firmware/src/main.cpp som sketch (kopiera hela src-mappen + include/)
3. Installera bibliotek: M5Unified, ArduinoJson, WebSockets (links2004), arduino-audio-tools, codec-helix
4. Överföra ZIP:en pocket-flash.zip eller hela src/ via USB-sticka
5. Select board: M5Stack-Core2, Port = COM-porten, Upload

## Alternativ 2: esptool (snabbast, klistra in kommando)
1. Python på skoldatorn: pip install esptool
2. Lägg 4 .bin-filer i en mapp (från pocket-flash.zip)
3. Kör (byt COMx till rätt port, kolla Enhetshanteraren):
   esptool.py --chip esp32 --port COMx --baud 460800 --connect-attempts 10 --before default_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x1000 bootloader.bin 0x8000 partitions.bin 0xe000 boot_app0.bin 0x10000 firmware.bin

Om "Connecting..." fastnar: håll G0 intryckt medan det står Connecting.
