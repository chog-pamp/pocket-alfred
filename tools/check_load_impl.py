#!/usr/bin/env python3
"""Trace _match_new_style_provider for freerouter step by step."""
import os, sys
os.environ['HERMES_HOME'] = '/home/leo/.hermes/profiles/alfred'
sys.path.insert(0, '/home/leo/.hermes/hermes-agent')

from hermes_cli.runtime_provider_custom import _entry_url, custom_provider_aliases, _normalize_custom_provider_name
from hermes_cli.config import is_provider_enabled
from hermes_cli.config import load_config_readonly

cfg = load_config_readonly()
providers = cfg.get('providers')
req = 'freerouter'
req_norm = req.strip().lower()
for ep_name, entry in providers.items():
    print('entry:', ep_name, entry)
    aliases = custom_provider_aliases(str(entry.get('name', '') or ep_name), str(ep_name))
    print('  aliases:', aliases)
    print('  req in aliases:', req_norm in aliases)
    print('  entry_url:', _entry_url(entry))
    print('  enabled:', is_provider_enabled(entry))
