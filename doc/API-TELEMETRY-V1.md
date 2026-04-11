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
Values drift ±0.1 °C every 5 s around the configured target (max ±2 °C).

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
