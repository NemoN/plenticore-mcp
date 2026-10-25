# Tool reference

Generated from the registered tools by `scripts/generate_tool_reference.py`.

The examples in [configuration.md](configuration.md) explain readings and settings. IDs must come from the connected inverter.

## `plenticore_battery`

Read available battery measurements, including SoC and power.

Access: Read.

Input schema:

```json
{
  "properties": {},
  "title": "batteryArguments",
  "type": "object"
}
```

## `plenticore_energy`

Read inverter-native energy counters for Day, Month, Year or Total. Preserve units.

Access: Read.

Input schema:

```json
{
  "properties": {
    "period": {
      "default": "Day",
      "enum": [
        "Day",
        "Month",
        "Year",
        "Total"
      ],
      "title": "Period",
      "type": "string"
    }
  },
  "title": "energyArguments",
  "type": "object"
}
```

## `plenticore_events`

Read the latest 1–100 inverter events; active events may have end_time=null.

Access: Read.

Input schema:

```json
{
  "properties": {
    "language": {
      "default": "de-de",
      "enum": [
        "de-de",
        "en-gb"
      ],
      "title": "Language",
      "type": "string"
    },
    "limit": {
      "default": 20,
      "title": "Limit",
      "type": "integer"
    }
  },
  "title": "eventsArguments",
  "type": "object"
}
```

## `plenticore_list_modules`

Discover the modules actually offered by this inverter and current user.

Access: Read.

Input schema:

```json
{
  "properties": {},
  "title": "list_modulesArguments",
  "type": "object"
}
```

## `plenticore_list_process_data`

Discover measurement IDs. Search module/ID; follow next_offset for more.

Access: Read.

Input schema:

```json
{
  "properties": {
    "limit": {
      "default": 200,
      "title": "Limit",
      "type": "integer"
    },
    "offset": {
      "default": 0,
      "title": "Offset",
      "type": "integer"
    },
    "query": {
      "default": "",
      "title": "Query",
      "type": "string"
    }
  },
  "title": "list_process_dataArguments",
  "type": "object"
}
```

## `plenticore_list_settings`

Discover setting types, units, access rights and min/max. Secrets are omitted.

Access: Read.

Input schema:

```json
{
  "properties": {
    "limit": {
      "default": 200,
      "title": "Limit",
      "type": "integer"
    },
    "offset": {
      "default": 0,
      "title": "Offset",
      "type": "integer"
    },
    "query": {
      "default": "",
      "title": "Query",
      "type": "string"
    }
  },
  "title": "list_settingsArguments",
  "type": "object"
}
```

## `plenticore_overview`

Read power flow, AC, PV strings, battery and meter measurements that exist.

Access: Read.

Input schema:

```json
{
  "properties": {},
  "title": "overviewArguments",
  "type": "object"
}
```

## `plenticore_read_process_data`

Read explicit {moduleid: [IDs]} (max 200), returning native values and units.

Access: Read.

Input schema:

```json
{
  "properties": {
    "selection": {
      "additionalProperties": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "title": "Selection",
      "type": "object"
    }
  },
  "required": [
    "selection"
  ],
  "title": "read_process_dataArguments",
  "type": "object"
}
```

## `plenticore_read_settings`

Read explicit {moduleid: [setting IDs]}. Discover IDs first; secrets are excluded.

Access: Read.

Input schema:

```json
{
  "properties": {
    "selection": {
      "additionalProperties": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "title": "Selection",
      "type": "object"
    }
  },
  "required": [
    "selection"
  ],
  "title": "read_settingsArguments",
  "type": "object"
}
```

## `plenticore_status`

Read API/firmware version and plant owner session status.

Access: Read.

Input schema:

```json
{
  "properties": {},
  "title": "statusArguments",
  "type": "object"
}
```

## `plenticore_update_settings`

Preview settings changes; dry_run=false writes and reads back. Values are strings.

Uses actual owner-accessible IDs, types and min/max. No installer login. Read list_settings
and the current values first. Multi-setting writes are not atomic; no automatic rollback.
A connection error after submission can leave a change applied: read back before retrying.

Access: Write (preview by default).

Input schema:

```json
{
  "properties": {
    "dry_run": {
      "default": true,
      "title": "Dry Run",
      "type": "boolean"
    },
    "moduleid": {
      "title": "Moduleid",
      "type": "string"
    },
    "values": {
      "additionalProperties": {
        "type": "string"
      },
      "title": "Values",
      "type": "object"
    }
  },
  "required": [
    "moduleid",
    "values"
  ],
  "title": "update_settingsArguments",
  "type": "object"
}
```

## Resource

`plenticore://usage` describes measurement interpretation and the settings workflow. It can be read without contacting the inverter.
