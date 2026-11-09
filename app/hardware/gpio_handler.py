import asyncio
from gpiozero import LED, Button

from app.services.button_service import button_service
from app.services.pullup_service import SET_GAP
from app.hardware.pins import BUTTON_CONFIGS, LED_PIN

# A flash inverts the LED briefly, so it shows whether the LED is on or off.
FLASH_SECONDS = 0.1
# One flash per pull-up press, two when a set or a distraction is saved.
SAVED_FLASHES = 2

class GPIOController:
  def __init__(self, state_manager):
    self.state_manager = state_manager
    self.led = LED(LED_PIN)
    self.buttons = []
    self._flash_steps = []
    self._set_end = None

    # Every button works the same way; what a press does is looked up when it
    # happens, so a change in the dashboard applies on the next press.
    for config in BUTTON_CONFIGS:
      print(
        f"Starting GPIO button '{config['label']}' on pin {config['pin']}"
      )
      button = Button(config["pin"], pull_up=True, bounce_time=0.05)
      button.when_pressed = self._build_press_handler(config["pin"])
      self.buttons.append(button)

    # will turn on or off from db info on init
    self._toggle_led()

  def _run_on_loop(self, handler):
    # gpiozero calls this from its own thread; database work runs on the app's loop.
    def handle_press():
      self.state_manager.loop.call_soon_threadsafe(
        lambda: asyncio.create_task(handler())
      )

    return handle_press

  def _build_press_handler(self, pin: int):
    return self._run_on_loop(lambda: self._handle_press_async(pin))

  def _toggle_led(self):
    if self.state_manager.is_clocked_in():
      self.led.on()
    else:
      self.led.off()

  def sync_led(self):
    self._toggle_led()

  def _show(self, lit: bool):
    if lit:
      self.led.on()
    else:
      self.led.off()

  def flash_led(self, times: int = 1):
    # Inverts the LED `times` times, then returns it to clocked in or out. A new
    # flash replaces one still running, so quick presses each show.
    for step in self._flash_steps:
      step.cancel()
    loop = self.state_manager.loop
    lit = self.state_manager.is_clocked_in()
    self._flash_steps = [
      loop.call_later(index * FLASH_SECONDS, self._show, lit if index % 2 else not lit)
      for index in range(times * 2)
    ]
    self._flash_steps.append(loop.call_later(times * 2 * FLASH_SECONDS, self.sync_led))

  async def _handle_press_async(self, pin: int):
    self.state_manager.announce_press(pin)
    # Read at press time, so a change in the dashboard applies right away.
    action = button_service.get_action(pin)
    if action == "pullup":
      await self._handle_pullup_async()
    elif action == "distraction":
      await self._handle_distraction_async()
    elif action == "activity":
      assignment = button_service.get(pin)
      await self.state_manager.toggle_activity(assignment["category_id"], assignment["tags"])
      self.sync_led()
    else:
      print(f"GPIO {pin} does nothing; pick what it does in the dashboard's Settings")

  async def _handle_pullup_async(self):
    await self.state_manager.record_pullup()
    self.flash_led()
    # Once the taps stop for a set's gap, a double flash confirms the set.
    if self._set_end is not None:
      self._set_end.cancel()
    self._set_end = self.state_manager.loop.call_later(
      SET_GAP.total_seconds(), lambda: self.flash_led(SAVED_FLASHES)
    )

  async def _handle_distraction_async(self):
    # Distractions belong to a session. No flash means nothing was counted.
    if await self.state_manager.record_distraction() is not None:
      self.flash_led(SAVED_FLASHES)

  def stop(self):
    print("stopping GPIO")
    for button in self.buttons:
      button.close()
    self.led.close()
