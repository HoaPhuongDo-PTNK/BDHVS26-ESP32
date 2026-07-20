import machine
import neopixel
import sys
import uselect
import utime

RGB_PIN = 48  
pin = machine.Pin(RGB_PIN, machine.Pin.OUT)
np = neopixel.NeoPixel(pin, 1)

def set_color(r, g, b):
    """Hàm đặt màu cho đèn LED RGB"""
    np[0] = (r, g, b)
    np.write()

set_color(0, 0, 0)

poll = uselect.poll()
poll.register(sys.stdin, uselect.POLLIN)

print("ESP32-S3 MicroPython Receiver Ready!")

while True:
    events = poll.poll(100)
    if events:
        lenh = sys.stdin.read(1)
        
        if lenh == '1':
            for _ in range(2):
                set_color(0, 255, 0)
                utime.sleep_ms(200)
                set_color(0, 0, 0)
                utime.sleep_ms(150)
                
        elif lenh == '0':
            set_color(255, 0, 0)