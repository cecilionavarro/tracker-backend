from gpiozero import LED, Button

from app.hardware.pins import BUTTON_PIN, LED_PIN

class GPIOController:
  def __init__(self, state_manager):
    print(f"Starting GPIO on pin {BUTTON_PIN}")
    self.state_manager = state_manager
    self.button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
    self.led = LED(LED_PIN)
    self.button.when_pressed = self.handle_press

  def handle_press(self):
    self.state_manager.toggle()

    if self.state_manager.is_clocked_in():
      self.led.on()
    else:
      self.led.off()

  def stop(self):
    print("stopping GPIO")
    self.button.close()
    self.led.close()