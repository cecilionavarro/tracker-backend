from datetime import datetime, timezone

class StateManager:
  def __init__(self):
    self.clocked_in = False
    self.started_at = None
  
  def is_clocked_in(self) -> bool:
    return self.clocked_in
  
  def clock_in(self) -> None:
    self.clocked_in = True
    self.started_at = datetime.now(timezone.utc)

  def clock_out(self) -> None:
    self.clocked_in = False

  def toggle(self) -> None:
    if self.clocked_in:
      self.clock_out()
    else:
      self.clock_in()
    print(self.clocked_in)
    print(self.started_at)