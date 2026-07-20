"""MicroPython Morse-code key firmware for the ESP32.

Press the button to send Morse code. The on-board LED mirrors the button
in real time, and the decoded text is streamed to the serial console.

Timing (all derived from a 0.1 s dot unit):
    dot   = 0.1 s press
    dash  = 0.3 s press
    symbol gap (inside a letter)  ~ 0.1 s silence
    letter gap                     ~ 0.3 s silence
    word gap                       ~ 0.7 s silence

The serial console (REPL) runs at 115200 baud.
"""

from machine import Pin
import utime

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

LED_PIN = 41
BUTTON_PIN = 42
BUTTON_ACTIVE_LOW = True  # PULL_UP button: pressed reads 0

SERIAL_BAUDRATE = 115200  # REPL / UART output baud rate

# Morse timing thresholds, in seconds.
DOT_TIME = 0.1            # duration of a dot press
DASH_TIME = 0.3           # duration of a dash press
UNIT = DOT_TIME           # base time unit

# Threshold used to classify a press as dot or dash (midpoint of the two).
DOT_DASH_THRESHOLD = (DOT_TIME + DASH_TIME) / 2.0   # 0.2 s

# Silence thresholds that separate a letter from the next letter / word.
LETTER_GAP = 3 * UNIT     # 0.3 s -> end of current letter
WORD_GAP = 7 * UNIT       # 0.7 s -> end of current word (emit a space)

# Software debounce for the mechanical button.
DEBOUNCE_S = 0.03

POLL_S = 0.002            # main loop poll interval

# ----------------------------------------------------------------------
# Morse table (code -> character)
# ----------------------------------------------------------------------

MORSE_TABLE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
    "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
    "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
    "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
    "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
    ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9",
}


def decode_symbols(symbols):
    return MORSE_TABLE.get(symbols, "?")


# ----------------------------------------------------------------------
# Hardware setup
# ----------------------------------------------------------------------

led = Pin(LED_PIN, Pin.OUT)
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)


def read_button_pressed():
    """Return the debounced logical pressed state of the button."""
    raw = button.value()
    if BUTTON_ACTIVE_LOW:
        return raw == 0
    return raw == 1


def main():
    print("Morse key ready. Press the button to send Morse code.")
    print("Baud: %d  LED_PIN: %d  BUTTON_PIN: %d"
          % (SERIAL_BAUDRATE, LED_PIN, BUTTON_PIN))

    # Debounce: hold a raw reading for DEBOUNCE_S before committing it.
    # Both edges are delayed equally, so measured press duration is preserved.
    stable_pressed = read_button_pressed()
    candidate = stable_pressed
    candidate_time = utime.ticks_ms()

    # Morse acquisition state.
    pressed = False
    press_start = 0
    current_symbols = ""
    last_release_time = None

    while True:
        now = utime.ticks_ms()

        # --- debounce the raw button reading ---
        raw_pressed = read_button_pressed()
        if raw_pressed != candidate:
            candidate = raw_pressed
            candidate_time = now
        if utime.ticks_diff(now, candidate_time) >= int(DEBOUNCE_S * 1000):
            stable_pressed = candidate

        # --- edge detection on the debounced state ---
        if stable_pressed and not pressed:
            # button went down
            pressed = True
            press_start = now
            led.value(1)
        elif not stable_pressed and pressed:
            # button went up
            pressed = False
            led.value(0)
            duration = utime.ticks_diff(now, press_start) / 1000.0
            symbol = "." if duration < DOT_DASH_THRESHOLD else "-"
            current_symbols += symbol
            last_release_time = now
        elif not pressed and current_symbols:
            # idle: decide letter / word boundaries from the silence
            if last_release_time is not None:
                gap = utime.ticks_diff(now, last_release_time) / 1000.0
                if gap >= WORD_GAP:
                    char = decode_symbols(current_symbols)
                    print(char + " ")  # trailing newline ends the word
                    current_symbols = ""
                    last_release_time = None
                elif gap >= LETTER_GAP:
                    char = decode_symbols(current_symbols)
                    print(char, end="")
                    current_symbols = ""
                    last_release_time = None

        utime.sleep(POLL_S)


if __name__ == "__main__":
    main()
