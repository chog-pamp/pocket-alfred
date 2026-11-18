import M5, network, esp32, time
M5.begin()
nvs = esp32.NVS('uiflow')
w = network.WLAN(network.STA_IF)
w.active(True)
if not w.isconnected():
    w.connect(nvs.get_str('ssid0'), nvs.get_str('pswd0'))
    for i in range(20):
        time.sleep(1)
        if w.isconnected():
            break
L = M5.Lcd
L.clear(0x0A0A0C)
L.setTextColor(0x64FFDA)
L.setTextSize(2)
L.setCursor(20, 100)
L.print('ALFRED ONLINE')
L.setTextColor(0x8A8A92)
L.setTextSize(1)
L.setCursor(20, 140)
L.print(str(w.ifconfig()[0]) + '  bat ' + str(M5.Power.getBatteryLevel()) + '%')
print('MAIN-RUNNING', w.ifconfig()[0])
