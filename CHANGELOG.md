# Журнал изменений

## 2026-04-27

- Реализовано per-door декодирование в `src/vehicle_can/decoders/t856.py`: состояние вычисляется отдельно для каждой двери, а не как глобальный `all-open/all-close`.
- Добавлена передача `Cache.DoorCount` в декодер через `src/vehicle_can/decoders/registry.py`; количество дверей берется из `[Cache].DoorCount`.
- Обновлена конфигурация `etc/telemetry-provider.toml`: `DoorCount=6` и введена per-door схема `Mapping.doors.door-map."<N>"` (`byte`, `shift`, `open-values`, `close-values`).
- Обновлены тесты `tests/test_decoder.py`, `tests/conftest.py`, `tests/test_api_endpoints.py` для сценариев 6 дверей и независимых состояний.
- Обновлена документация `doc/CONFIGURATION.md`, `doc/API-TELEMETRY-V1.md`, `README.md` под per-door модель.

## 2026-04-26

- Заархивирован документный битовый декодер дверей T856 как `src/vehicle_can/decoders/t856.py.bydoc.arvhived`; в шапке добавлено пояснение, что он соответствует формальному PDF, но не используется в продакшене.
- Переработано декодирование дверей в `src/vehicle_can/decoders/t856.py`: используется эмпирическая карта кодов из полевых дампов (`can0-doors-dump.txt`, `can0-doors-dump-2.txt`), и добавлена шапка с описанием новой карты.
- В `etc/telemetry-provider.toml` добавлены настраиваемые ключи сопоставления дверей:
  - `door-count`
  - `probe-bytes`
  - `open-codes`
  - `close-codes`
  - `unknown-state`
- Обновлены тесты декодера в `tests/test_decoder.py`: использованы payload, похожие на реальные дампы, и добавлен тест перехода `все закрыты -> все открыты -> все закрыты`.
