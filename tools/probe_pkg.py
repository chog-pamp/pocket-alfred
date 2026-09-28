"""Probe the openwakeword package layout in the training venv."""
import openwakeword, os, pkgutil
print(openwakeword.__file__)
print("modules:", [m.name for m in pkgutil.iter_modules(openwakeword.__path__)])
import openwakeword.utils as u
print("utils attrs:", [a for a in dir(u) if not a.startswith('_')])
try:
    import openwakeword.custom_model as cm
    print("custom_model attrs:", [a for a in dir(cm) if not a.startswith('_')])
except Exception as e:
    print("custom_model:", e)
try:
    import openwakeword.featurize_and_train as ft
    print("featurize_and_train OK:", [a for a in dir(ft) if not a.startswith('_')][:20])
except Exception as e:
    print("featurize_and_train:", e)
from openwakeword.model import Model
import inspect
print("Model.predict sig:", inspect.signature(Model.predict))
print("Model init sig:", inspect.signature(Model.__init__))
