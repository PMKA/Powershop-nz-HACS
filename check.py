"""
Pre-push static checks for the Powershop HA integration.
Runs without Home Assistant installed — uses lightweight stubs.

Usage:
    python check.py

Exits with code 0 on success, 1 on any failure.
"""
import ast
import sys
import os
import importlib
import types
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

COMPONENT_FILES = [
    "custom_components/powershop/__init__.py",
    "custom_components/powershop/api.py",
    "custom_components/powershop/config_flow.py",
    "custom_components/powershop/const.py",
    "custom_components/powershop/sensor.py",
    "custom_components/powershop/strings.json",
    "custom_components/powershop/manifest.json",
]

errors = []

# ── 1. Syntax check every Python file ────────────────────────────────────────
print("[ 1 ] Syntax checking Python files...")
for rel in COMPONENT_FILES:
    path = os.path.join(ROOT, rel)
    if not rel.endswith(".py"):
        continue
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=path)
        print(f"      OK  {rel}")
    except SyntaxError as e:
        errors.append(f"SYNTAX ERROR in {rel}: {e}")
        print(f"      FAIL {rel}: {e}")

# ── 2. JSON validity ──────────────────────────────────────────────────────────
import json
print("[ 2 ] Validating JSON files...")
for rel in COMPONENT_FILES:
    if not rel.endswith(".json"):
        continue
    path = os.path.join(ROOT, rel)
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        print(f"      OK  {rel}")
    except json.JSONDecodeError as e:
        errors.append(f"JSON ERROR in {rel}: {e}")
        print(f"      FAIL {rel}: {e}")

# ── 3. Import check (with HA stubs) ──────────────────────────────────────────
print("[ 3 ] Import checking with HA stubs...")

def _make_stub(mod_name, **attrs):
    m = types.ModuleType(mod_name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[mod_name] = m
    return m

_sentinel = object()

_make_stub("homeassistant")
_make_stub("homeassistant.core", HomeAssistant=type("HomeAssistant", (), {}))
_make_stub("homeassistant.config_entries",
    ConfigEntry=type("ConfigEntry", (), {"data": {}}),
    ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}),
)
_make_stub("homeassistant.helpers")
_make_stub("homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=type("DataUpdateCoordinator", (), {"__init__": lambda *a, **k: None}),
    CoordinatorEntity=type("CoordinatorEntity", (), {"__init__": lambda *a, **k: None}),
    UpdateFailed=type("UpdateFailed", (Exception,), {}),
)
_make_stub("homeassistant.helpers.entity_platform",
    AddEntitiesCallback=type("AddEntitiesCallback", (), {}),
)
_make_stub("homeassistant.helpers.aiohttp_client")
_make_stub("homeassistant.helpers.entity",
    Entity=type("Entity", (), {}),
)
_make_stub("homeassistant.components")
_make_stub("homeassistant.components.sensor",
    SensorEntity=type("SensorEntity", (), {}),
    SensorEntityDescription=type("SensorEntityDescription", (), {
        "__init__": lambda self, **kw: self.__dict__.update(kw)
    }),
    SensorDeviceClass=type("SensorDeviceClass", (), {"MONETARY": "monetary", "ENERGY": "energy", "POWER": "power"}),
    SensorStateClass=type("SensorStateClass", (), {"MEASUREMENT": "measurement", "TOTAL": "total", "TOTAL_INCREASING": "total_increasing"}),
)
_make_stub("homeassistant.const",
    Platform=types.SimpleNamespace(SENSOR="sensor"),
    CURRENCY_DOLLAR="$",
    CONF_EMAIL="email",
    UnitOfEnergy=types.SimpleNamespace(KILO_WATT_HOUR="kWh"),
)
_make_stub("homeassistant.exceptions",
    HomeAssistantError=Exception,
    ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (Exception,), {}),
    ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}),
)
_make_stub("homeassistant.data_entry_flow",
    FlowResult=dict,
    FlowResultType=types.SimpleNamespace(FORM="form", CREATE_ENTRY="create_entry", ABORT="abort"),
)
_make_stub("homeassistant.config_entries",
    ConfigEntry=type("ConfigEntry", (), {"data": {}}),
    ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}),
    ConfigFlow=type("ConfigFlow", (), {"__init_subclass__": classmethod(lambda *a, **k: None)}),
    OptionsFlow=type("OptionsFlow", (), {}),
)
_make_stub("aiohttp",
    ClientSession=type("ClientSession", (), {}),
    ClientTimeout=type("ClientTimeout", (), {"__init__": lambda self, **k: None}),
)
_make_stub("voluptuous",
    Schema=lambda x, extra=None: x,
    Required=lambda x, **kw: x,
    Optional=lambda x, **kw: x,
    In=lambda x: x,
    All=lambda *a: a[0],
    Length=lambda **kw: (lambda x: x),
)

modules_to_import = [
    "custom_components.powershop.const",
    "custom_components.powershop.api",
    "custom_components.powershop.sensor",
    "custom_components.powershop.config_flow",
]

for mod in modules_to_import:
    try:
        if mod in sys.modules:
            del sys.modules[mod]
        importlib.import_module(mod)
        print(f"      OK  {mod}")
    except Exception as e:
        errors.append(f"IMPORT ERROR in {mod}: {e}")
        print(f"      FAIL {mod}: {e}")
        traceback.print_exc()

# ── 4. Key symbol checks ──────────────────────────────────────────────────────
print("[ 4 ] Checking key symbols exist...")

checks = [
    ("custom_components.powershop.api", "PowershopAPIClient"),
    ("custom_components.powershop.api", "AuthError"),
    ("custom_components.powershop.api", "OTPError"),
    ("custom_components.powershop.sensor", "PowershopDataUpdateCoordinator"),
    ("custom_components.powershop.sensor", "SENSORS"),
    ("custom_components.powershop.sensor", "async_setup_entry"),
    ("custom_components.powershop.const", "DOMAIN"),
    ("custom_components.powershop.const", "CONF_ACCOUNT_NUMBER"),
    ("custom_components.powershop.const", "CONF_PROPERTY_ID"),
    ("custom_components.powershop.const", "CONF_REFRESH_TOKEN"),
]

for mod_name, symbol in checks:
    try:
        mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
        if not hasattr(mod, symbol):
            raise AttributeError(f"'{symbol}' not found in {mod_name}")
        print(f"      OK  {mod_name}.{symbol}")
    except Exception as e:
        errors.append(f"SYMBOL ERROR: {e}")
        print(f"      FAIL {e}")

# ── 5. Manifest version matches changelog ─────────────────────────────────────
print("[ 5 ] Checking manifest version...")
try:
    manifest_path = os.path.join(ROOT, "custom_components/powershop/manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    version = manifest.get("version", "")
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    if f"### v{version}" in readme:
        print(f"      OK  manifest version {version} found in README changelog")
    else:
        errors.append(f"VERSION MISMATCH: manifest is v{version} but README has no matching changelog entry")
        print(f"      WARN manifest is v{version} but README has no '### v{version}' changelog entry")
except Exception as e:
    errors.append(f"VERSION CHECK ERROR: {e}")
    print(f"      FAIL {e}")

# ── Result ────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("All checks passed.")
    sys.exit(0)
