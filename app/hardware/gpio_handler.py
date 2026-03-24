import asyncio
from gpiozero import LED, Button

from app.hardware.pins import BUTTON_PIN, LED_PIN

class GPIOController:
  def __init__(self, state_manager):
    print(f"Starting GPIO on pin {BUTTON_PIN}")
    self.state_manager = state_manager
    self.button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
    self.led = LED(LED_PIN)
    self.button.when_pressed = self.handle_press

    # will turn on or off from db info on init
    self._toggle_led()

  def handle_press(self):
    self.state_manager.loop.call_soon_threadsafe(
      lambda: asyncio.create_task(self._handle_press_async())
    )

  def _toggle_led(self):
    if self.state_manager.is_clocked_in():
      self.led.on()
    else:
      self.led.off()

  async def _handle_press_async(self):
    await self.state_manager.toggle()

    self._toggle_led()

  def stop(self):
    print("stopping GPIO")
    self.button.close()
    self.led.close()