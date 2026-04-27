# Конфигурация сервиса (`telemetry-provider.toml`)

Полное описание параметров примера [etc/telemetry-provider.toml](../etc/telemetry-provider.toml) и того, как загрузчик в [src/models/data_models.py](../src/models/data_models.py) интерпретирует TOML.

Имена ключей в файле — **как в примере** (PascalCase в секциях); в коде они преобразуются в поля `snake_case`.

---

## Соответствие строкам `etc/telemetry-provider.toml`

Ниже — **каждый параметр**, который встречается в примере [etc/telemetry-provider.toml](../etc/telemetry-provider.toml) (включая закомментированные шаблоны). Обязательность: для работы сервиса достаточно секций, которые уже есть в примере; отсутствующие ключи подставляются из столбца «По умолчанию» в таблицах ниже.

| Строка в примере | Секция | Параметр | Обязателен |
|------------------|--------|----------|------------|
| `Host = ...` | `[API]` | `Host` | нет (есть дефолт) |
| `HTTP_Port = ...` | `[API]` | `HTTP_Port` | нет |
| `Workers = ...` | `[API]` | `Workers` | нет |
| `ProgramDirectory = ...` | `[System]` | `ProgramDirectory` | нет |
| `LogDir = ...` | `[System]` | `LogDir` | нет |
| `DisableCan = ...` | `[System]` | `DisableCan` | нет |
| `Interface = ...` | `[CAN]` | `Interface` | нет |
| `Channel = ...` | `[CAN]` | `Channel` | нет |
| `Profile = ...` | `[CAN]` | `Profile` | нет |
| `Bitrate = ...` | `[CAN]` | `Bitrate` | нет (можно опустить — возьмётся из `Profile`) |
| `FD = ...` | `[CAN]` | `FD` | нет |
| `Decoder = ...` | `[CAN]` | `Decoder` | нет |
| `ReceiveTimeout = ...` | `[CAN]` | `ReceiveTimeout` | нет |
| `StaleAfterSeconds = ...` | `[Cache]` | `StaleAfterSeconds` | нет |
| `DefaultDoorState = ...` | `[Cache]` | `DefaultDoorState` | нет |
| `CoalesceByFrame = ...` | `[Cache]` | `CoalesceByFrame` | нет |
| `DoorCount = ...` | `[Cache]` | `DoorCount` | нет |
| `# MinIntervalPerPgnMs = ...` | `[Cache]` | `MinIntervalPerPgnMs` | опционально |
| `# ProcessEveryNFrames = ...` | `[Cache]` | `ProcessEveryNFrames` | опционально |
| `TemperatureMode = ...` | `[Telemetry]` | `TemperatureMode` | нет |
| `SimTargetInside = ...` | `[Telemetry]` | `SimTargetInside` | нет |
| `SimTargetOutside = ...` | `[Telemetry]` | `SimTargetOutside` | нет |
| `SimTickSeconds = ...` | `[Telemetry]` | `SimTickSeconds` | нет |
| `SimStepC = ...` | `[Telemetry]` | `SimStepC` | нет |
| `SimMaxDriftC = ...` | `[Telemetry]` | `SimMaxDriftC` | нет |
| закомментированный блок `[Mapping]` | `[Mapping]` | см. раздел ниже | нужен при `Decoder = dbc` / `bus-fms` и работе с DBC |

Секция **`[Mapping]`** в примере целиком в комментариях: для декодеров **`noop`** она не нужна. Для **`dbc`** и **`bus-fms`** без раскомментированного `dbc_path` (и без существующего файла) декодер **не** обновит кэш из шины.

---

## Секция `[API]` — HTTP-сервер

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `Host` | строка | `0.0.0.0` | Адрес привязки uvicorn: все интерфейсы или конкретный IP (например `127.0.0.1`). |
| `HTTP_Port` | целое | `7080` | TCP-порт REST API (как в [API-TELEMETRY-V1.md](API-TELEMETRY-V1.md)). |
| `Workers` | целое | `1` | Число процессов uvicorn из конфига. **Важно:** кэш телеметрии хранится в памяти одного процесса; при `Workers > 1` приложение **принудительно использует один воркер** и пишет предупреждение в лог. Оставьте `1`. |

---

## Секция `[System]` — окружение и режим без шины

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `ProgramDirectory` | строка | `/usr/local/can-telemetry` | Служебный каталог приложения (как в шаблоне NMEA-проекта). **Текущая версия сервиса не читает его из кода**; можно использовать в скриптах установки/юнитах systemd. |
| `LogDir` | строка | `logs` | Каталог для файла логов `can-telemetry.log` (создаётся при старте, если возможно). |
| `DisableCan` | логическое | `false` | Если `true`, **шина CAN не открывается** и задача чтения кадров не выполняет полезной работы (остаётся в цикле с пустым `bus`). Удобно для разработки API и CI. Температурная симуляция при `TemperatureMode = simulated` продолжает работать. |

---

## Секция `[CAN]` — транспорт SocketCAN и выбор декодера

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `Interface` | строка | `socketcan` | Бэкенд `python-can` (обычно `socketcan` для `can0` / `vcan0` в Linux). |
| `Channel` | строка | `can0` | Имя интерфейса ядра (например `can0`, `vcan0`). |
| `Profile` | строка | `bus-fms` | **Подсказка физического уровня**, не заменяет декодер. Значения `bus-fms` / `bus_fms`: если **`Bitrate` не задан или ≤ 0**, подставляется **250000** бит/с (типично для FMS / Bus-FMS). Любой другой профиль без явного `Bitrate` даёт **500000** бит/с. |
| `Bitrate` | целое | из `Profile` | Скорость шины в бит/с. Имеет приоритет над автоподстановкой из `Profile`. |
| `FD` | логическое | `false` | Передать в `python-can` признак CAN FD (если драйвер и оборудование поддерживают). |
| `Decoder` | строка | `noop` | **Семантика разбора кадров**: встроенное имя (`noop`, `bus-fms`, `dbc`, …) или **FQN класса** `модуль:ИмяКласса` (см. раздел ниже). |
| `ReceiveTimeout` | число с плавающей точкой | `0.5` | Таймаут **в секундах** для `bus.recv()` в цикле чтения. При тишине на шине поток периодически просыпается, что упрощает отмену задачи и снижает риск вечной блокировки. |

Параметры вроде размера буфера приёмника (`SocketRxBuffer` из проектного плана) **в текущей версии в TOML не читаются**; при необходимости их можно добавить в `open_bus` позже.

---

## Секция `[Cache]` — кэш телеметрии и throttle

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `StaleAfterSeconds` | число | `30.0` | Максимальный **возраст данных** (по `time.monotonic()` с момента последнего обновления поля). **Двери:** если старше — в API отдаётся `unknown`. **Задняя:** при устаревании в API отдаётся `reverse = false`. **Температура (режим `can`):** устаревшие зоны **исключаются** из объекта `temperatures` (пустой объект, если ничего свежего нет). В режиме `simulated` для температур устаревание к ответу не применяется. |
| `DefaultDoorState` | строка | `unknown` | Начальное состояние каждой двери до первого кадра; должно быть одним из `unknown`, `open`, `close` (как в контракте API). |
| `CoalesceByFrame` | логическое | `true` | Зарезервировано под политику «один кадр — одна атомарная запись». **Сейчас** вся обработка кадра и так выполняется под одной блокировкой `asyncio.Lock` в цикле чтения; флаг оставлен для совместимости с планом и возможного расширения. |
| `DoorCount` | целое | `4` | Сколько дверей отображать в кэше и в `GET .../doors/state` — ключи `"1"` … `"N"`. |
| `MinIntervalPerPgnMs` | целое, опционально | нет | Минимальный интервал **в миллисекундах** между **успешными** декодированиями кадров с одним и тем же ключом throttle. Ключ для **расширенного** 29-битного ID — извлечённый **PGN** (J1939); для стандартного 11-битного — сам `arbitration_id`. Если с последнего приёма прошло меньше порога, кадр пропускается (декодер не вызывается). |
| `ProcessEveryNFrames` | целое, опционально | нет | Обрабатывать только каждый **N-й** кадр с данным PGN/`arbitration_id` (счётчик нарастает на каждый кадр). Имеет смысл при `N > 1`. Сочетается с логикой `MinIntervalPerPgnMs` в одной функции throttle. |

---

## Секция `[Telemetry]` — температура: шина или симуляция

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `TemperatureMode` | строка | `simulated` | `simulated` — фоновая задача двигает `inside` / `outside` вокруг целей (см. ниже). `can` — значения зон обновляет только декодер из CAN; симуляция не запускается. Регистр не важен. |
| `SimTargetInside` | число | `22.0` | Целевая температура зоны `inside` (°C) для симуляции. |
| `SimTargetOutside` | число | `15.0` | Целевая температура зоны `outside` (°C) для симуляции. |
| `SimTickSeconds` | число | `5.0` | Период **в секундах** между шагами симуляции (согласуется с описанием API «каждые 5 с»). |
| `SimStepC` | число | `0.1` | Шаг изменения за один тик (°C), знак выбирается случайно, пока не упрётся в предел дрейфа. |
| `SimMaxDriftC` | число | `2.0` | Максимальное отклонение от цели (°C) в каждую сторону. |

---

## Секция `[Mapping]` — данные для декодера

Вся секция загружается как **один словарь** `mapping` и передаётся в `decoder.configure(mapping)`. **Смысл ключей зависит от выбранного `Decoder`.** Для встроенных декодеров `bus-fms` и `dbc` (оба используют [DbcGenericDecoder](../src/vehicle_can/decoders/dbc_generic.py)) поддерживается следующее.

### Общие ключи DBC-декодера

| Ключ | Альтернативное имя | Описание |
|------|-------------------|----------|
| `dbc_path` | `DbcPath` | Абсолютный или относительный путь к файлу **DBC**. Без существующего файла декодер остаётся неактивным (кадры игнорируются). |
| `signal_map` | `SignalMap` | Вложенная таблица TOML: соответствие **полей API** именам **сигналов в DBC**. |

### Таблица `signal_map` (для `dbc` / `bus-fms`)

Ключи слева — **фиксированные имена**, значения — **точные имена сигналов** из DBC (как в файле).

| Ключ в TOML | Назначение |
|-------------|------------|
| `door_1` … `door_N` | Состояние двери с номером `N` в ответе API. Значение сигнала: число `0`/`1`, строки `open`/`close`/`closed`, и т.п. (см. логику `_door_from_value` в коде). |
| `reverse` | Задняя передача: число или булево представление; строки `1`/`true`/`on` трактуются как включено. |
| `inside` | Температура зоны `inside` (°C), приводится к `float`. |
| `outside` | Температура зоны `outside` (°C). |

Пример:

```toml
[Mapping]
dbc_path = "/etc/vehicle/bus-fms.dbc"

[Mapping.signal_map]
door_1 = "DoorOpen1"
door_2 = "DoorOpen2"
reverse = "ReverseGearSw"
inside = "CabinTemp"
outside = "AmbientAirTemp"
```

Декодер **`noop`** секцию `[Mapping]` не использует.

### Встроенные декодеры `dbc` и `bus-fms`

По коду это один и тот же [DbcGenericDecoder](../src/vehicle_can/decoders/dbc_generic.py): разбор кадра через **cantools** и `decode_message(arbitration_id, data)`. Имя **`bus-fms`** удобно в конфиге как «профиль общественного транспорта / FMS»; имя **`dbc`** — как нейтральное. Настройка **`[Mapping]`** для обоих одинакова.

**Ограничение:** один DBC-файл на конфиг; сигналы из **разных** сообщений (разные `BO_` / PGN) обрабатываются по мере прихода кадров — для каждого кадра `decode_message` возвращает только сигналы этого сообщения. Если имя из `signal_map` не входит в текущее сообщение, поле просто не обновляется на этом кадре (это нормально).

---

## Подключение новой спецификации CAN (новый декодер)

Цель: сменить формат/семантику шины **без правок** HTTP-маршрутов и цикла `recv`, только новым модулем и настройками.

---

## Параметры T856 в `kebab-case`

При `Decoder = "t856"` используются подсекции `[Mapping.temperature]`, `[Mapping.doors]`, `[Mapping.reverse]`.

### `[System]`

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `debug` | bool | `false` | Включает подробное логирование декодера T856. В лог пишутся значения **после расчета/усреднения**, но **до нормализации API**. |

### `[Mapping.temperature]`

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `queue-len` | int | `5` | Длина очереди для усреднения (скользящее среднее по последним значениям). |
| `average-all-zone` | bool | `true` | Если `true`, `inside` = среднее по всем выбранным датчикам. |
| `sensors` | `"all"` или `int[]` | `"all"` | Какие датчики салона учитывать (`1`, `2`). |
| `interior-default-value` | float/null | `null` | Значение `inside` при неизвестных/устаревших данных CAN. `null` => поле не выводится. |
| `exterior-default-value` | float/null | `null` | Значение `outside` при неизвестных/устаревших данных CAN. `null` => поле не выводится. |
| `interior-normalize-min` | float | `-40` | Нижняя граница нормализации `inside` на API-слое. |
| `interior-normalize-max` | float | `210` | Верхняя граница нормализации `inside` на API-слое. |
| `interior-normalize-fallback-min` | float | `-50` | Значение `inside` в API, если ниже `interior-normalize-min`. |
| `interior-normalize-fallback-max` | float | `250` | Значение `inside` в API, если выше `interior-normalize-max`. |
| `exterior-normalize-min` | float | `-40` | Нижняя граница нормализации `outside` на API-слое. |
| `exterior-normalize-max` | float | `210` | Верхняя граница нормализации `outside` на API-слое. |
| `exterior-normalize-fallback-min` | float | `-50` | Значение `outside` в API, если ниже `exterior-normalize-min`. |
| `exterior-normalize-fallback-max` | float | `250` | Значение `outside` в API, если выше `exterior-normalize-max`. |

Правило валидации:
- если `average-all-zone=false` и при этом `sensors` содержит несколько датчиков, это ошибка конфигурации. Декодер пишет ошибку в лог и принудительно включает `average-all-zone=true`.

### `[Mapping.reverse]`

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `reverse-code` | int | `124` | Код ETC2 для `reverse=true`. Все остальные коды дают `reverse=false`. |

### `[Mapping.ids]`

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `doors` | `int|string|array` | `0x18FF6527` | ID кадров для дверей. Поддерживаются десятичные и hex-строки (`"0x1BFFD880"`). |
| `io` | `int|string|array` | `0x18FF6427` | ID кадров для IO/передачи (поле `reverse`). |
| `temperatures1` | `int|string|array` | `0x18FF6227` | ID кадров для блока температур T856. |
| `match-mode` | `arbitration-id` \| `pgn` | `arbitration-id` | Режим сопоставления: точный CAN ID или совпадение по J1939 PGN (игнорирует Source Address). |

Примечание: это нужно для случаев, когда в реальной шине тот же PGN передается с другим SA/ID, чем в базовой спецификации.

### `[Mapping.doors]`

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `unknown-state` | `unknown \| open \| close` | `unknown` | Состояние для нераспознанного поля двери. |
| `door-map."<N>".byte` | int (0..7) | авто | Индекс байта payload для двери `N`. |
| `door-map."<N>".shift` | int (`0/2/4/6`) | авто | Сдвиг 2-битного поля двери `N` в выбранном байте. |
| `door-map."<N>".open-values` | array[int] | `[3]` | Какие 2-битные значения считать `open`. |
| `door-map."<N>".close-values` | array[int] | `[0,1,2]` | Какие 2-битные значения считать `close`. |

Примечания:
- Количество дверей берется только из `[Cache].DoorCount`.
- Если `door-map` не задан, используется эмпирическая схема для 6 дверей:
  - `d1=(byte0,shift2)`, `d2=(byte0,shift4)`, `d3=(byte0,shift6)`,
  - `d4=(byte4,shift2)`, `d5=(byte4,shift4)`, `d6=(byte4,shift6)`.

Пример:

```toml
[System]
debug = true

[Mapping.temperature]
queue-len = 5
average-all-zone = true
sensors = "all"
interior-default-value = null
exterior-default-value = null
interior-normalize-min = -40
interior-normalize-max = 210
interior-normalize-fallback-min = -50
interior-normalize-fallback-max = 250
exterior-normalize-min = -40
exterior-normalize-max = 210
exterior-normalize-fallback-min = -50
exterior-normalize-fallback-max = 250

[Mapping.doors]
unknown-state = "unknown"

[Mapping.doors.door-map."1"]
byte = 0
shift = 2
open-values = [3]
close-values = [0, 1, 2]

[Mapping.doors.door-map."2"]
byte = 0
shift = 4
open-values = [3]
close-values = [0, 1, 2]

[Mapping.doors.door-map."3"]
byte = 0
shift = 6
open-values = [3]
close-values = [0, 1, 2]

[Mapping.doors.door-map."4"]
byte = 4
shift = 2
open-values = [3]
close-values = [0, 1, 2]

[Mapping.ids]
doors = ["0x18FF6527"]
io = ["0x18FF6427"]
temperatures1 = ["0x18FF6227"]
match-mode = "arbitration-id"

[Mapping.reverse]
reverse-code = 124
```

### Шаг 0. Выбор пути: только DBC или свой декодер

- Если данные описываются **существующим DBC** (J1939 / Bus-FMS / OEM) и достаточно сопоставить сигналы полям API — используйте **`Decoder = "dbc"`** или **`bus-fms`**, раскомментируйте и заполните **`[Mapping]`** (см. подпроцедуру ниже). Код в репозитории менять не нужно.
- Если нужна **другая логика** (несколько DBC, битовые маски без DBC, расшифровка вне cantools) — добавьте **свой класс** декодера (шаги 1–2).

### Шаг 1. Реализовать класс декодера

- Разместите файл в пакете `src/vehicle_can/decoders/` (имя пакета **не** `can`, чтобы не перекрывать `python-can`).
- Класс должен иметь:
  - `configure(self, mapping: dict) -> None` — прочитать свою часть конфигурации (пути, таблицы, флаги).
  - `decode_frame(self, msg, cache) -> None` — **синхронный** метод: принимает объект сообщения `python-can` (`msg.arbitration_id`, `msg.data`, `msg.is_extended_id`, …) и обновляет [TelemetryCache](../src/telemetry/cache.py) через **`cache.set_door` / `set_reverse` / `set_temperature`**.  
  Эти методы вызываются **только когда уже удерживается** `cache.lock` в [runner_task](../src/runner_task.py); не вызывайте их из других потоков без той же договорённости.

### Шаг 2. Зарегистрировать декодер или указать FQN

**Вариант A.** Добавить короткое имя в `BUILTIN_DECODERS` в [registry.py](../src/vehicle_can/decoders/registry.py):

```python
BUILTIN_DECODERS = {
    ...
    "my-oem": MyOemDecoder,
}
```

**Вариант B.** Не менять реестр: установить в конфиге полный путь к классу:

```toml
Decoder = "my_company.decoders.oem:MyOemDecoder"
```

Класс должен быть импортируем (установленный пакет или `PYTHONPATH`).

### Шаг 3. Указать декодер и физику шины в TOML

```toml
[CAN]
Decoder = "my-oem"   # или FQN
Profile = "bus-fms"  # при необходимости автобитрейт 250k
Bitrate = 250000     # явно, если нужно другое значение
```

### Шаг 4. Заполнить `[Mapping]` под ваш декодер

**4.1. Для встроенного DBC-декодера (`dbc` / `bus-fms`)**

1. Получите файл **`.dbc`** (поставщик ТС, Bus-FMS/J1939 матрица, экспорт из инструмента).
2. Убедитесь, что **имена сигналов** в DBC совпадают с теми, что вы укажете в TOML (регистр и символы важны).
3. Раскомментируйте и задайте **`dbc_path`**: лучше **абсолютный** путь на целевой машине; относительный разрешается от **текущей рабочей директории** процесса при старте сервиса.
4. Заполните **`[Mapping.signal_map]`**:
   - ключи **`door_1` … `door_N`** должны покрывать нужные двери; `N` не обязан совпадать с `DoorCount`, но ключи в API — только `"1"`…`"DoorCount"` из `[Cache]`.
   - **`reverse`**, **`inside`**, **`outside`** — по необходимости; отсутствующие ключи просто не маппятся.
5. Установите **`Decoder = "dbc"`** (или **`bus-fms`**).
6. При необходимости включите **`TemperatureMode = "can"`**, чтобы температура с шины не смешивалась с симуляцией.

**4.2. Проверка DBC без запуска сервиса (рекомендуется)**

В интерактивном Python (из корня проекта, `PYTHONPATH=src`):

```python
import cantools
db = cantools.database.load_file("/path/to/file.dbc")
# подставьте реальный arbitration_id и данные кадра:
db.decode_message(0x18FEF100, bytes(8), decode_choices=False)
```

Если выбрасывается исключение или нужного сигнала нет в словаре — исправьте DBC, ID или длину полезной нагрузки до настройки TOML.

**4.3. Для собственного декодера**

- Задокументируйте в README модуля или в отдельном файле **схему `[Mapping]`**: обязательные и необязательные ключи, типы значений, пример TOML.
- В `configure()` разберите `mapping` вручную: например `mapping.get("bit_rules")`, `mapping.get("extra_dbc_path")` и т.д.
- Произвольные ключи верхнего уровня в `[Mapping]` допустимы: загрузчик передаёт весь поддерево секции одним словарём (вложенные таблицы TOML — вложенные `dict`).

**4.4. Вынесенный файл маппинга**

Сейчас загрузчик читает **один** основной TOML. Чтобы хранить маппинг отдельно, в `configure()` можно прочитать второй файл, если в `[Mapping]` передать, например, `mapping_file = "/etc/vehicle/mapping.toml"` (такой ключ нужно поддержать в вашем декодере или расширить общий загрузчик позже).

### Шаг 5. Проверка на шине и по API

1. Поднимите интерфейс: `sudo ip link set can0 up type can bitrate 250000` или `vcan0` для тестов.
2. Убедитесь, что **`DisableCan = false`** и **`Channel`** совпадает с интерфейсом.
3. Генерируйте трафик (`cansend`, запись с шины, симулятор).
4. Проверьте `GET http://<host>:7080/api/telemetry/v1/doors/state` (и остальные маршруты): значения должны обновляться; при остановке трафика через **`StaleAfterSeconds`** двери уходят в `unknown`, задняя — в `false` (см. таблицу `[Cache]`).

### Типичные проблемы

| Симптом | Что проверить |
|---------|----------------|
| Двери всегда `unknown` | Декодер `noop`; нет `dbc_path`; неверный путь к DBC; имена сигналов в `signal_map` не совпадают с DBC; кадры с другим `arbitration_id`. |
| Температура не с шины | `TemperatureMode = simulated`; декодер не вызывает `set_temperature`; в `signal_map` нет `inside`/`outside`. |
| Ошибка при старте с FQN | Опечатка в `модуль:Класс`; модуль не в `PYTHONPATH`. |

---

## Связь с REST API

Поведение полей ответов описано в [API-TELEMETRY-V1.md](API-TELEMETRY-V1.md). Конфигурация определяет только источник и свежесть данных в кэше, а не формат JSON (имена ключей верхнего уровня фиксированы контрактом; составные ключи при необходимости проходят через kebab-case в [api_server.py](../src/api_server.py)).
