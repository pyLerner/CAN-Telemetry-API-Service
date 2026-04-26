#!/bin/bash

INTERFACE="can0"
# Список стандартных скоростей для проверки
SPEEDS=(1000000 500000 250000 125000 100000 50000)

# Задежка для прослушивания
LISTEN_DELAY=10

echo "=== Старт поиска Bitrate на $INTERFACE ==="

for BITRATE in "${SPEEDS[@]}"; do
    echo "----------------------------------------"
    echo "⚙️ Настройка $INTERFACE на $BITRATE bps..."
    
    # Остановка и запуск на новой скорости в пассивном режиме
    sudo ip link set "$INTERFACE" down 2>/dev/null
    sudo ip link set "$INTERFACE" type can bitrate "$BITRATE" listen-only on 2>/dev/null
    sudo ip link set "$INTERFACE" up 2>/dev/null
    
    echo "📊 Запуск candump на $LISTEN_DELAY секунд..."
    # Фоновое прослушивание
    timeout $LISTEN_DELAY candump "$INTERFACE" &
    PID=$!
    
    # Ожидаем завершения таймаута
    wait $PID 2>/dev/null
    
    echo -e "\n❓ Данные читаются на скорости $BITRATE? [y/N]: "
    read -r -n 1 user_choice
    echo "" # Перенос строки после ввода
    
    if [[ "$user_choice" =~ ^[Yy]$ ]]; then
        echo "✅ Успех! Скорость $BITRATE сохранена."
        echo "🔄 Переводим интерфейс в нормальный режим (Active)..."
        sudo ip link set "$INTERFACE" down
        sudo ip link set "$INTERFACE" type can bitrate "$BITRATE" listen-only off
        sudo ip link set "$INTERFACE" up
        echo "🟢 Готово! Интерфейс $INTERFACE готов к полноценной работе на $BITRATE bps."
        exit 0
    fi
done

echo "❌ Перебор завершен. Подходящая скорость не найдена."
sudo ip link set "$INTERFACE" down
