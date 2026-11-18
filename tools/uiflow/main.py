# ============================================================
#  Pocket Alfred — Enzo pet UI (UIFlow2 / MicroPython, Core2)
#  ------------------------------------------------------------
#  Editable in the UIFlow2 Web IDE (uiflow2.m5stack.com) or any
#  MicroPython tooling. Structure:
#
#    1. CONFIG            — colors, paths, timing (edit freely)
#    2. HARDWARE          — WiFi + battery
#    3. ENZO PET          — sprite frames + animation engine
#    4. SCREENS           — pet screen, battery screen
#    5. INPUT             — touch zones + swipe
#    6. ACTION HOOKS      — on_talk_start/on_talk_end (wire gadget here)
#    7. MAIN LOOP
#
#  States: idle · listening · transcribing · thinking · speaking · lowbat
# ============================================================
import os, sys, time
import M5
import network
import esp32

# ------------------------------------------------------------
# 1. CONFIG
# ------------------------------------------------------------
BG          = 0x0A0A0C     # near-black
FG          = 0xE8E8EC     # main text
MUTED       = 0x8A8A92     # secondary text
DIM         = 0x3A3A42     # hints
GREEN       = 0x64FFDA     # mint  — listening
BLUE        = 0x4FC3F7     # blue  — thinking
YELLOW      = 0xFFD54F     # yellow— speaking
PURPLE      = 0xBA68C8     # purple— transcribing
RED         = 0xFF5252     # red   — low battery
GRAY        = 0x8A8A92     # idle

PET_W, PET_H   = 96, 104
PET_X          = 112        # (320-96)/2
PET_FOOT_Y     = 200        # feet line on 240-tall screen

FPS_SLOW       = 150        # ms per frame, idle/breathing
FPS_FAST       = 100        # ms per frame, active states
LOWBAT_PCT     = 20         # below this = faint animation + red

STATE_LABEL = {
    "idle":         "Alfred",
    "listening":    "Listening...",
    "transcribing": "Transcribing...",
    "thinking":     "Thinking...",
    "speaking":     "Replying...",
    "lowbat":       "Low battery!",
}
STATE_COLOR = {
    "idle": GRAY, "listening": GREEN, "transcribing": PURPLE,
    "thinking": BLUE, "speaking": YELLOW, "lowbat": RED,
}

ACTIONS = {                   # ← add more states/frames here if you extend Enzo
    "idle":         ["/flash/enzo/idle_%d.png", 6],
    "listening":    ["/flash/enzo/listening_%d.png", 6],
    "transcribing": ["/flash/enzo/transcribing_%d.png", 6],
    "thinking":     ["/flash/enzo/thinking_%d.png", 8],
    "speaking":     ["/flash/enzo/speaking_%d.png", 4],
    "lowbat":       ["/flash/enzo/lowbat_%d.png", 8],
}

# ------------------------------------------------------------
# 2. HARDWARE — WiFi + battery
# ------------------------------------------------------------
def connect_wifi():
    nvs = esp32.NVS("uiflow")
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if not w.isconnected():
        w.connect(nvs.get_str("ssid0"), nvs.get_str("pswd0"))
        for _ in range(20):
            time.sleep(1)
            if w.isconnected():
                break
    return w

def battery_pct():
    try:
        return int(M5.Power.getBatteryLevel())
    except Exception:
        return 0

# ------------------------------------------------------------
# 3. ENZO PET — frame drawing
# ------------------------------------------------------------
def draw_pet(state, frame):
    path = ACTIONS[state][0] % frame
    try:
        M5.Lcd.drawImage(path, PET_X, PET_FOOT_Y - PET_H)
    except Exception as e:
        print("pet draw fail", path, e)

# ------------------------------------------------------------
# 4. SCREENS
# ------------------------------------------------------------
screen = "pet"      # "pet" | "battery"
state  = "idle"     # pet animation state
transcript = ""     # last heard text (shown under pet)
status = ""         # live status phrase ("Searching the web")

def draw_pet_screen():
    L = M5.Lcd
    L.clear(BG)
    # header: ALFRED + status dot (pulses with state color)
    L.setTextColor(MUTED)
    L.setTextSize(1)
    L.setCursor(12, 8)
    L.print("ALFRED")
    L.setTextColor(STATE_COLOR[state])
    L.fillCircle(308, 12, 4, STATE_COLOR[state])
    # status line under the pet
    L.setTextColor(STATE_COLOR[state])
    L.setTextSize(2)
    L.setCursor(60, 208)
    label = STATE_LABEL[state]
    if state == "idle" and transcript:
        label = transcript[-28:]
        L.setTextSize(1)
        L.setCursor(60, 214)
    L.print(label)
    if status and state in ("thinking", "transcribing"):
        L.setTextColor(BLUE)
        L.setTextSize(1)
        L.setCursor(60, 226)
        L.print(status[:40])
    # battery mini-bar, top right
    draw_battery_bar(228, 6, 60, 10, battery_pct())
    draw_pet(state, frame)

def draw_battery_bar(x, y, w, h, pct):
    L = M5.Lcd
    L.drawRect(x, y, w, h, MUTED)
    c = GREEN if pct > 40 else (YELLOW if pct > 15 else RED)
    L.fillRect(x + 2, y + 2, int((w - 4) * pct / 100), h - 4, c)
    L.fillRect(x + w + 2, y + h // 4, 3, h // 2, MUTED)
    L.setTextColor(MUTED)
    L.setTextSize(1)
    L.setCursor(x - 30, y + 1)
    L.print(str(pct) + "%")

def draw_battery_screen():
    L = M5.Lcd
    L.clear(BG)
    pct = battery_pct()
    L.setTextColor(FG)
    L.setTextSize(2)
    L.setCursor(96, 60)
    L.print("BATTERY")
    # big meter
    bx, by, bw, bh = 60, 100, 200, 40
    L.drawRect(bx, by, bw, bh, MUTED)
    c = GREEN if pct > 40 else (YELLOW if pct > 15 else RED)
    if pct > 0:
        L.fillRect(bx + 3, by + 3, int((bw - 6) * pct / 100), bh - 6, c)
    L.fillRect(bx + bw + 4, by + bh // 4, 6, bh // 2, MUTED)
    L.setTextColor(FG)
    L.setTextSize(3)
    L.setCursor(130, 152)
    L.print(str(pct) + "%")
    L.setTextColor(MUTED)
    L.setTextSize(1)
    L.setCursor(84, 200)
    L.print("swipe = back to Alfred")
    if pct <= LOWBAT_PCT:
        draw_pet("lowbat", frame)   # Enzo faints

# ------------------------------------------------------------
# 5. INPUT — bottom zones + swipe
# ------------------------------------------------------------
def handle_touch():
    global screen
    t = M5.Touch.getDetail()
    if t.state == 2:          # touch_end
        return
    x, y = t.x, t.y
    if t.state == 1:          # touch_end fires separately; use hold logic below
        pass

# (touch_begin/end handled in main loop; zones only on pet screen)

# ------------------------------------------------------------
# 6. ACTION HOOKS — wire the gadget protocol here later
# ------------------------------------------------------------
def on_talk_start():
    """Called when the middle zone is pressed (hold-to-talk)."""
    set_state("listening")
    print("[talk] start")        # TODO: gadget audio.start + stream PCM16 frames

def on_talk_end(duration_s):
    """Called on release / silence / 10 s cap."""
    set_state("transcribing")
    print("[talk] end", duration_s)   # TODO: audio.end → transcript/reply events
    time.sleep_ms(1200)
    set_state("idle")

def set_state(s):
    global state, frame, last_frame_ms
    state = s
    frame = 0
    last_frame_ms = time.ticks_ms()
    draw_pet_screen()

# ------------------------------------------------------------
# 7. MAIN LOOP
# ------------------------------------------------------------
M5.begin()
M5.Lcd.setRotation(0)
w = connect_wifi()

frame = 0
last_frame_ms = time.ticks_ms()
draw_pet_screen()
print("ALFRED-UI-ONLINE", w.ifconfig()[0], "bat", battery_pct())

touching = False
talk_t0 = 0
last_x = -1
last_y = -1
prev_touch = 0

while True:
    M5.update()

    # ── touch (count-transition based — works across UIFlow2 state enums) ──
    cnt = 0
    try:
        cnt = M5.Touch.getCount()
    except Exception:
        pass
    if cnt > 0 and prev_touch == 0:
        try:
            t = M5.Touch.getDetail()
            last_x, last_y = t.x, t.y
        except Exception:
            last_x, last_y = -1, -1
        touching = True
        if screen == "pet" and state in ("idle",) and last_y > 170:
            if 107 <= last_x < 214:           # middle = talk (hold)
                talk_t0 = time.ticks_ms()
                on_talk_start()
            elif last_x < 107:                # left = cancel (placeholder)
                print("[btn] cancel")
            else:                             # right = new session (placeholder)
                print("[btn] new session")
    elif cnt == 0 and prev_touch > 0 and touching:
        dx, dy = 0, 0
        try:
            t = M5.Touch.getDetail()
            dx = t.x - last_x
            dy = t.y - last_y
        except Exception:
            pass
        if state == "listening":
            on_talk_end((time.ticks_ms() - talk_t0) / 1000)
        elif abs(dx) > 60 and abs(dx) > abs(dy):
            screen = "battery" if screen == "pet" else "pet"
            if screen == "pet":
                draw_pet_screen()
            else:
                draw_battery_screen()
        touching = False
        last_x = -1
    prev_touch = cnt

    # talk cap: 10 s max
    if state == "listening" and time.ticks_diff(time.ticks_ms(), talk_t0) > 10000:
        on_talk_end(10.0)

    # ── animation ──
    fps = FPS_SLOW if state == "idle" else FPS_FAST
    if time.ticks_diff(time.ticks_ms(), last_frame_ms) >= fps:
        last_frame_ms = time.ticks_ms()
        n = ACTIONS[state][1]
        frame = (frame + 1) % n
        if screen == "pet":
            draw_pet(state, frame)
            # pulsing header dot
            import math
            p = 0.6 + 0.4 * abs(math.sin(time.ticks_ms() / 260))
            c = STATE_COLOR[state]
            r5 = int(((c >> 11) & 0x1F) * p)
            g5 = int(((c >> 5) & 0x3F) * p)
            b5 = int((c & 0x1F) * p)
            M5.Lcd.fillCircle(308, 12, 4, (r5 << 11) | (g5 << 5) | b5)
        elif screen == "battery" and battery_pct() <= LOWBAT_PCT:
            draw_pet("lowbat", frame)
