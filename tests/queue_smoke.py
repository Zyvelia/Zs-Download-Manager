from types import SimpleNamespace
from neon.ui import MainWindow
class Worker:
    status = 'Queued'
    def __init__(self, name, started): self.name=name; self.started=started; self.running=False
    def isRunning(self): return self.running
    def start(self): self.running=True; self.started.append(self.name)
started=[]
cards=[]
for name,priority in [('low',0),('normal',1),('high',2),('other',1)]:
    obj=Worker(name,started); cards.append(SimpleNamespace(data={'kind':'HTTP'},obj=obj,priority=priority,created=len(cards)))
MainWindow.pump_queue(SimpleNamespace(cards=cards))
assert started == ['high','normal','other'], started
print('Priority queue starts highest-priority waiting transfers first: PASS')
