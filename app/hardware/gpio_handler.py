import asyncio
from gpiozero import LED, Button

from app.hardware.pins import BUTTON_CONFIGS, LED_PIN

class GPIOController:
  def __init__(self, state_manager):
    self.state_manager = state_manager
    self.led = LED(LED_PIN)
    self.buttons = []

    for config in BUTTON_CONFIGS:
      print(
        f"Starting GPIO button '{config['label']}' on pin {config['pin']}"
      )
      button = Button(config["pin"], pull_up=True, bounce_time=0.05)
      button.when_pressed = self._build_press_handler(
        config["category"],
        config.get("tags", ""),
      )
      self.buttons.append(button)

    # will turn on or off from db info on init
    self._toggle_led()

  def _build_press_handler(self, category: str, tags: str = ""):
    def handle_press():
      self.state_manager.loop.call_soon_threadsafe(
        lambda: asyncio.create_task(self._handle_press_async(category, tags))
      )

    return handle_press

  def _toggle_led(self):
    if self.state_manager.is_clocked_in():
      self.led.on()
    else:
      self.led.off()

  def sync_led(self):
    self._toggle_led()

  async def _handle_press_async(self, category: str, tags: str = ""):
    await self.state_manager.toggle_activity(category, tags)

    self.sync_led()

  def stop(self):
    print("stopping GPIO")
    for button in self.buttons:
      button.close()
    self.led.close()
