@echo off
:loop
    python Food_bot.py
    echo Бот перезапускается...
    timeout /t 2
goto loop
