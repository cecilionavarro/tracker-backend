from gpiozero import LED, Button

from app.hardware.pins import BUTTON_PIN, LED_PIN

class GPIOController:
  def __init__(self):
    self.button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
    self.led = LED(LED_PIN)