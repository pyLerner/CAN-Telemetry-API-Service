# Telemetry API Reference

Base URL: `http://<host>:7080`

All responses use **kebab-case** JSON naming.

---

## Health Check

### `GET /api/ping`

Returns service liveness status.

**Response** `200 OK`

```json
{
  "running": "ok",
  "timestamp": "2025-07-15T12:00:00+00:00"
}
```

---

## Doors

### `GET /api/telemetry/v1/doors/state`

Returns current state of all doors.  
For T856 decoder: any state except `closed` is reported as `open`.

**Response** `200 OK`

```json
{
  "doors": {
    "1": "close",
    "2": "open",
    "3": "close",
    "4": "close"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `doors` | `object` | Door number (1-based) → `DoorState` |

`DoorState` values: `unknown`, `open`, `close`

---

## Gear

### `GET /api/telemetry/v1/gear/state`

Returns current reverse gear state.  
For T856 decoder: `reverse=true` only when ETC2 gear code equals `124` (Назад); otherwise `false`.

**Response** `200 OK`

```json
{
  "reverse": false
}
```

| Field | Type | Description |
|---|---|---|
| `reverse` | `boolean` | `true` = reverse gear engaged |

---

## Temperature

### `GET /api/telemetry/v1/temperature/state`

Returns current temperature readings per zone.

For T856 decoder:
- `inside` is calculated from Temperatures1 cabin sensors using queue average.
- `outside` is calculated from Temperatures1 external field (`factor 0.03125`, `offset -273`) and averaged by queue.
- API applies configurable normalization thresholds/fallbacks from `Mapping.temperature`.
- In `System.debug=true`, logs contain values after calculation/averaging and before normalization.

**Response** `200 OK`

```json
{
  "temperatures": {
    "inside": 22.3,
    "outside": 14.8
  }
}
```

| Field | Type | Description |
|---|---|---|
| `temperatures` | `object` | `TemperatureZone` → Celsius reading |

`TemperatureZone` values: `inside`, `outside` (extensible)
