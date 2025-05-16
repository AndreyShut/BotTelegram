#!/bin/bash

# Максимальное количество перезапусков
MAX_RESTARTS=10
# Задержка между перезапусками (в секундах)
RESTART_DELAY=5

echo "Запуск бота с автоматическим перезапуском..."

restarts=0
while [ $restarts -lt $MAX_RESTARTS ]; do
    echo "Запуск бота (попытка $((restarts + 1))/$MAX_RESTARTS)..."
    python3 main.py
    
    EXIT_CODE=$?
    echo "Бот завершил работу с кодом $EXIT_CODE"
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Бот завершил работу нормально. Выход."
        exit 0
    else
        echo "Бот упал. Перезапуск через $RESTART_DELAY сек..."
        sleep $RESTART_DELAY
        ((restarts++))
    fi
done

echo "Достигнуто максимальное количество перезапусков ($MAX_RESTARTS). Бот остановлен."
exit 1