"""Init AudioFeatures (downloads shared melspectrogram+embedding models on first use)."""
import sys, os
sys.path.insert(0, "/home/leo/homelab/pocket-alfred/tools")
import openwakeword.utils
F = openwakeword.utils.AudioFeatures()
print("embedding shape for 3s:", F.get_embedding_shape(3))
print("OK, models cached at:", os.path.expanduser("~/.openwakeword") if os.path.isdir(os.path.expanduser("~/.openwakeword")) else os.environ.get("XDG_CACHE_HOME", "~/.cache")+"/openwakeword")
