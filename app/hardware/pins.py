LED_PIN = 17

# Every button wired to the Pi, by GPIO number, and its job on the first
# start. Each is wired the same way: one leg to the GPIO pin, the other to
# ground, using the internal pull-up. After the first start, each button's job
# lives in MongoDB and changes in the dashboard's Settings; editing the action,
# category, or tags here no longer has an effect.
#
# Actions: "activity" clocks in and out of a category and tag, "pullup" and
# "distraction" count one each press, and "none" does nothing.
BUTTON_CONFIGS = (
  {
    "pin": 2,
    "action": "activity",
    "category": "pianiso",
    "tags": "technical",
    "label": "Pianiso Technical",
  },
  {
    "pin": 3,
    "action": "activity",
    "category": "pianiso",
    "tags": "non_technical",
    "label": "Pianiso Non-Technical",
  },
  {
    "pin": 4,
    "action": "activity",
    "category": "creating",
    "tags": "",
    "label": "Creating",
  },
  {
    "pin": 27,
    "action": "activity",
    "category": "toycon",
    "tags": "",
    "label": "Toycon",
  },
  {"pin": 22, "action": "pullup", "label": "Pull-up counter"},          # physical pin 15
  {"pin": 23, "action": "distraction", "label": "Distraction counter"},  # physical pin 16
)
