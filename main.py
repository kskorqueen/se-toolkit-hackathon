import os
import sqlite3
import random
import re
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database helpers (raw sqlite3, no ORM)
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "explanations.db"


def init_db():
    """Create the explanations table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            explanation TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'ru',
            category TEXT NOT NULL DEFAULT 'other'
        )
        """
    )
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Yield a connection wrapped in a context manager with auto-commit/close."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
def detect_language(text: str) -> str:
    """Detect if text is Russian (has Cyrillic) or English."""
    if re.search('[а-яА-ЯёЁ]', text):
        return 'ru'
    return 'en'


# ---------------------------------------------------------------------------
# Simple explanation engine (no LLM) — bilingual
# ---------------------------------------------------------------------------
# Structure: key -> {"ru": "...", "en": "..."}
# Keys can be in Russian or English — both map to the same entry
EXPLANATIONS = {
    # === Computer & Hardware / Компьютер и железо ===
    "robot": {"ru": "🤖 Робот — это как механический помощник! Представь игрушечную машинку, которая сама ездит и убирает игрушки по команде. Роботы помогают людям на заводе, дома и даже в космосе!",
              "en": "🤖 A robot is like a mechanical helper! Imagine a toy car that drives around and cleans up toys on its own. Robots help people in factories, at home, and even in space!"},
    "робот": {"ru": "🤖 Робот — это как механический помощник! Представь игрушечную машинку, которая сама ездит и убирает игрушки по команде. Роботы помогают людям на заводе, дома и даже в космосе!",
              "en": "🤖 A robot is like a mechanical helper! Imagine a toy car that drives around and cleans up toys on its own. Robots help people in factories, at home, and even in space!"},
    "computer": {"ru": "💻 Компьютер — это умная коробка, которая умеет думать! Как если бы у тебя был волшебный блокнот, который рисует, считает и показывает мультики по твоей просьбе.",
                 "en": "💻 A computer is a smart box that can think! It's like having a magic notebook that draws, counts, and shows cartoons whenever you ask."},
    "компьютер": {"ru": "💻 Компьютер — это умная коробка, которая умеет думать! Как если бы у тебя был волшебный блокнот, который рисует, считает и показывает мультики по твоей просьбе.",
                  "en": "💻 A computer is a smart box that can think! It's like having a magic notebook that draws, counts, and shows cartoons whenever you ask."},
    "процессор": {"ru": "⚡ Процессор — это мозг компьютера! Он думает быстрее всех на свете — за одну секунду делает миллионы вычислений.",
                  "en": "⚡ A processor is the brain of a computer! It thinks faster than anyone — doing millions of calculations in one second."},
    "processor": {"ru": "⚡ Процессор — это мозг компьютера! Он думает быстрее всех на свете — за одну секунду делает миллионы вычислений.",
                  "en": "⚡ A processor is the brain of a computer! It thinks faster than anyone — doing millions of calculations in one second."},
    "память": {"ru": "🧩 Память компьютера — как твой рюкзак! Чем он больше, тем больше вещей (программ) можно положить и быстро достать.",
               "en": "🧩 Computer memory is like your backpack! The bigger it is, the more stuff (programs) you can put in and quickly grab."},
    "memory": {"ru": "🧩 Память компьютера — как твой рюкзак! Чем он больше, тем больше вещей (программ) можно положить и быстро достать.",
               "en": "🧩 Computer memory is like your backpack! The bigger it is, the more stuff (programs) you can put in and quickly grab."},
    "мышь": {"ru": "🖱️ Компьютерная мышь — это твой палец на экране! Двигаешь её рукой, а курсор на экране повторяет. Как волшебная указка!",
             "en": "🖱️ A computer mouse is like your finger on the screen! You move it with your hand, and the cursor follows. Like a magic pointer!"},
    "mouse": {"ru": "🖱️ Компьютерная мышь — это твой палец на экране! Двигаешь её рукой, а курсор на экране повторяет. Как волшебная указка!",
              "en": "🖱️ A computer mouse is like your finger on the screen! You move it with your hand, and the cursor follows. Like a magic pointer!"},
    "клавиатура": {"ru": "⌨️ Клавиатура — это панель с буквами и цифрами! Ты нажимаешь кнопки, а на экране появляются слова. Как печатная машинка, только современная!",
                   "en": "⌨️ A keyboard is a panel with letters and numbers! You press buttons and words appear on the screen. Like a modern typewriter!"},
    "keyboard": {"ru": "⌨️ Клавиатура — это панель с буквами и цифрами! Ты нажимаешь кнопки, а на экране появляются слова. Как печатная машинка, только современная!",
                 "en": "⌨️ A keyboard is a panel with letters and numbers! You press buttons and words appear on the screen. Like a modern typewriter!"},
    "монитор": {"ru": "🖥️ Монитор — это экран, на котором компьютер показывает тебе всё, что делает. Как телевизор, только ты можешь им управлять!",
                "en": "🖥️ A monitor is the screen where the computer shows you everything it does. Like a TV, but you can control it!"},
    "monitor": {"ru": "🖥️ Монитор — это экран, на котором компьютер показывает тебе всё, что делает. Как телевизор, только ты можешь им управлять!",
                "en": "🖥️ A monitor is the screen where the computer shows you everything it does. Like a TV, but you can control it!"},
    "жёсткий диск": {"ru": "💾 Жёсткий диск — это большой сундук, где компьютер хранит все свои сокровища: игры, фотки и мультики. Даже когда его выключают — всё остаётся!",
                     "en": "💾 A hard drive is a big treasure chest where the computer stores all its goodies: games, photos, and movies. Even when turned off — everything stays!"},
    "hard drive": {"ru": "💾 Жёсткий диск — это большой сундук, где компьютер хранит все свои сокровища: игры, фотки и мультики. Даже когда его выключают — всё остаётся!",
                   "en": "💾 A hard drive is a big treasure chest where the computer stores all its goodies: games, photos, and movies. Even when turned off — everything stays!"},
    "видеокарта": {"ru": "🎮 Видеокарта — это художник внутри компьютера! Она рисует все картинки, игры и мультики на экране. Чем она круче — тем красивее картинка!",
                   "en": "🎮 A graphics card is the artist inside your computer! It draws all the pictures, games, and animations on screen. The cooler it is — the more beautiful the picture!"},
    "graphics card": {"ru": "🎮 Видеокарта — это художник внутри компьютера! Она рисует все картинки, игры и мультики на экране. Чем она круче — тем красивее картинка!",
                      "en": "🎮 A graphics card is the artist inside your computer! It draws all the pictures, games, and animations on screen. The cooler it is — the more beautiful the picture!"},
    "динамики": {"ru": "🔊 Динамики — это рот компьютера! Через них он разговаривает, играет музыку и показывает мультики со звуком.",
                 "en": "🔊 Speakers are the mouth of the computer! Through them, it talks, plays music, and shows cartoons with sound."},
    "speakers": {"ru": "🔊 Динамики — это рот компьютера! Через них он разговаривает, играет музыку и показывает мультики со звуком.",
                 "en": "🔊 Speakers are the mouth of the computer! Through them, it talks, plays music, and shows cartoons with sound."},
    "usb": {"ru": "🔌 USB — это универсальный разъём, как розетка для электроприборов. Через него можно подключить мышку, клавиатуру, флешку и даже зарядить телефон!",
            "en": "🔌 USB is a universal connector, like a power outlet for electronics. You can plug in a mouse, keyboard, flash drive, and even charge your phone!"},
    "ноутбук": {"ru": "💼 Ноутбук — это компьютер, который можно носить с собой! Он складывается как книжка и работает от батарейки — как портативный телевизор.",
                "en": "💼 A laptop is a computer you can carry with you! It folds like a book and runs on battery — like a portable TV."},
    "laptop": {"ru": "💼 Ноутбук — это компьютер, который можно носить с собой! Он складывается как книжка и работает от батарейки — как портативный телевизор.",
               "en": "💼 A laptop is a computer you can carry with you! It folds like a book and runs on battery — like a portable TV."},
    "планшет": {"ru": "📱 Планшет — это большой телефон без кнопки звонка! На нём удобно рисовать пальцем, смотреть мультики и играть.",
                "en": "📱 A tablet is like a big phone without the call button! It's great for drawing with your finger, watching cartoons, and playing games."},
    "tablet": {"ru": "📱 Планшет — это большой телефон без кнопки звонка! На нём удобно рисовать пальцем, смотреть мультики и играть.",
               "en": "📱 A tablet is like a big phone without the call button! It's great for drawing with your finger, watching cartoons, and playing games."},
    "железо": {"ru": "🔧 Железо — это всё, что можно потрогать! Компьютер, телефон, роутер — это железо. А программы, которые нельзя потрогать — это софт.",
               "en": "🔧 Hardware is everything you can touch! A computer, phone, router — that's hardware. Programs you can't touch — that's software."},
    "hardware": {"ru": "🔧 Железо — это всё, что можно потрогать! Компьютер, телефон, роутер — это железо. А программы, которые нельзя потрогать — это софт.",
                 "en": "🔧 Hardware is everything you can touch! A computer, phone, router — that's hardware. Programs you can't touch — that's software."},
    "бит": {"ru": "💡 Бит — это самая маленькая частичка информации! Он может быть либо 0, либо 1. Как лампочка: либо горит, либо нет. Компьютер работает с миллиардами битов!",
            "en": "💡 A bit is the tiniest piece of information! It can be either 0 or 1. Like a light bulb: either on or off. A computer works with billions of bits!"},
    "bit": {"ru": "💡 Бит — это самая маленькая частичка информации! Он может быть либо 0, либо 1. Как лампочка: либо горит, либо нет. Компьютер работает с миллиардами битов!",
            "en": "💡 A bit is the tiniest piece of information! It can be either 0 or 1. Like a light bulb: either on or off. A computer works with billions of bits!"},
    "гигабайт": {"ru": "📦 Гигабайт — это единица памяти! Один гигабайт — это примерно 200 песен или 500 фотографий. Чем больше гигабайт — тем больше вещей влезет в телефон.",
                  "en": "📦 A gigabyte is a unit of storage! One gigabyte is about 200 songs or 500 photos. The more gigabytes — the more stuff fits in your phone."},
    "gigabyte": {"ru": "📦 Гигабайт — это единица памяти! Один гигабайт — это примерно 200 песен или 500 фотографий. Чем больше гигабайт — тем больше вещей влезет в телефон.",
                 "en": "📦 A gigabyte is a unit of storage! One gigabyte is about 200 songs or 500 photos. The more gigabytes — the more stuff fits in your phone."},
    "рам": {"ru": "🧠 RAM — это оперативная память! Это как рабочий стол: чем он больше, тем больше задач можно делать одновременно. Но когда компьютер выключается — всё с рабочего стола исчезает!",
            "en": "🧠 RAM is short-term memory! It's like a desk: the bigger it is, the more tasks you can do at once. But when the computer turns off — everything on the desk disappears!"},
    "ram": {"ru": "🧠 RAM — это оперативная память! Это как рабочий стол: чем он больше, тем больше задач можно делать одновременно. Но когда компьютер выключается — всё с рабочего стола исчезает!",
            "en": "🧠 RAM is short-term memory! It's like a desk: the bigger it is, the more tasks you can do at once. But when the computer turns off — everything on the desk disappears!"},
    "драйвер": {"ru": "🔌 Драйвер — это переводчик между устройством и компьютером! Как если бы принтер говорил на своём языке, а драйвер переводит его команды для компьютера.",
                "en": "🔌 A driver is a translator between a device and the computer! Like if a printer spoke its own language, and the driver translates its commands for the computer."},
    "driver": {"ru": "🔌 Драйвер — это переводчик между устройством и компьютером! Как если бы принтер говорил на своём языке, а драйвер переводит его команды для компьютера.",
               "en": "🔌 A driver is a translator between a device and the computer! Like if a printer spoke its own language, and the driver translates its commands for the computer."},
    "операционная система": {"ru": "🖥️ Операционная система — это главный менеджер компьютера! Windows, macOS, Linux — они управляют всеми программами и железом. Как дирижёр в оркестре!",
                            "en": "🖥️ An operating system is the main manager of a computer! Windows, macOS, Linux — they manage all programs and hardware. Like a conductor in an orchestra!"},
    "operating system": {"ru": "🖥️ Операционная система — это главный менеджер компьютера! Windows, macOS, Linux — они управляют всеми программами и железом. Как дирижёр в оркестре!",
                         "en": "🖥️ An operating system is the main manager of a computer! Windows, macOS, Linux — they manage all programs and hardware. Like a conductor in an orchestra!"},
    "os": {"ru": "🖥️ Операционная система — это главный менеджер компьютера! Windows, macOS, Linux — они управляют всеми программами и железом. Как дирижёр в оркестре!",
           "en": "🖥️ An operating system is the main manager of a computer! Windows, macOS, Linux — they manage all programs and hardware. Like a conductor in an orchestra!"},

    # === Internet & Web / Интернет и веб ===
    "internet": {"ru": "🌐 Интернет — это невидимые ниточки, которые соединяют все компьютеры в мире! Как если бы ты мог шепнуть другу на другом конце города, а он бы услышал.",
                 "en": "🌐 The internet is invisible threads connecting all computers in the world! Like being able to whisper to a friend across town and they'd hear you."},
    "интернет": {"ru": "🌐 Интернет — это невидимые ниточки, которые соединяют все компьютеры в мире! Как если бы ты мог шепнуть другу на другом конце города, а он бы услышал.",
                 "en": "🌐 The internet is invisible threads connecting all computers in the world! Like being able to whisper to a friend across town and they'd hear you."},
    "сайт": {"ru": "🌍 Сайт — это страничка в интернете! Как страница в книге, только живая — там можно нажимать кнопки, смотреть видео и играть.",
             "en": "🌍 A website is a page on the internet! Like a page in a book, but alive — you can press buttons, watch videos, and play."},
    "site": {"ru": "🌍 Сайт — это страничка в интернете! Как страница в книге, только живая — там можно нажимать кнопки, смотреть видео и играть.",
             "en": "🌍 A website is a page on the internet! Like a page in a book, but alive — you can press buttons, watch videos, and play."},
    "website": {"ru": "🌍 Сайт — это страничка в интернете! Как страница в книге, только живая — там можно нажимать кнопки, смотреть видео и играть.",
                "en": "🌍 A website is a page on the internet! Like a page in a book, but alive — you can press buttons, watch videos, and play."},
    "браузер": {"ru": "🌐 Браузер — это окно в интернет! Через него ты заходишь на сайты, смотришь видео и играешь. Chrome, Firefox — всё это браузеры.",
                "en": "🌐 A browser is a window to the internet! Through it, you visit websites, watch videos, and play games. Chrome, Firefox — those are all browsers."},
    "browser": {"ru": "🌐 Браузер — это окно в интернет! Через него ты заходишь на сайты, смотришь видео и играешь. Chrome, Firefox — всё это браузеры.",
                "en": "🌐 A browser is a window to the internet! Through it, you visit websites, watch videos, and play games. Chrome, Firefox — those are all browsers."},
    "облако": {"ru": "☁️ Облако — это когда твои фотки и файлы живут не в телефоне, а на больших компьютерах далеко-далеко. Но ты можешь достать их откуда угодно!",
               "en": "☁️ The cloud is when your photos and files live not on your phone, but on big computers far away. But you can access them from anywhere!"},
    "cloud": {"ru": "☁️ Облако — это когда твои фотки и файлы живут не в телефоне, а на больших компьютерах далеко-далеко. Но ты можешь достать их откуда угодно!",
              "en": "☁️ The cloud is when your photos and files live not on your phone, but on big computers far away. But you can access them from anywhere!"},
    "приложение": {"ru": "📱 Приложение — это маленькая программка внутри телефона! Как игрушка внутри kinder-сюрприза — открываешь и пользуешься.",
                   "en": "📱 An app is a little program inside your phone! Like a toy inside a surprise egg — you open it and use it."},
    "app": {"ru": "📱 Приложение — это маленькая программка внутри телефона! Как игрушка внутри kinder-сюрприза — открываешь и пользуешься.",
            "en": "📱 An app is a little program inside your phone! Like a toy inside a surprise egg — you open it and use it."},
    "application": {"ru": "📱 Приложение — это маленькая программка внутри телефона! Как игрушка внутри kinder-сюрприза — открываешь и пользуешься.",
                    "en": "📱 An app is a little program inside your phone! Like a toy inside a surprise egg — you open it and use it."},
    "wifi": {"ru": "📶 Wi-Fi — это невидимый интернет-кабель! Вместо провода воздух приносит тебе мультики и игры прямо на телефон.",
             "en": "📶 Wi-Fi is an invisible internet cable! Instead of a wire, the air brings cartoons and games right to your phone."},
    "bluetooth": {"ru": "🔵 Bluetooth — это как короткая невидимая ниточка между устройствами. Через неё наушники слышат музыку от телефона без проводов!",
                  "en": "🔵 Bluetooth is like a short invisible thread between devices. Through it, headphones hear music from your phone without wires!"},
    "поисковик": {"ru": "🔍 Поисковик — это волшебная книга, которая знает ответы на все вопросы! Пишешь слово — и она сразу показывает, где найти нужное.",
                  "en": "🔍 A search engine is a magic book that knows answers to all questions! You type a word — and it instantly shows where to find what you need."},
    "search engine": {"ru": "🔍 Поисковик — это волшебная книга, которая знает ответы на все вопросы! Пишешь слово — и она сразу показывает, где найти нужное.",
                      "en": "🔍 A search engine is a magic book that knows answers to all questions! You type a word — and it instantly shows where to find what you need."},
    "email": {"ru": "✉️ Email — это электронное письмо! Как бумажное письмо, только летит со скоростью молнии и приходит за секунду.",
              "en": "✉️ Email is an electronic letter! Like a paper letter, but it flies at the speed of lightning and arrives in a second."},
    "ссылка": {"ru": "🔗 Ссылка — это волшебная дверь! Нажимаешь — и попадаешь на другую страничку. Как портал в другой мир!",
               "en": "🔗 A link is a magic door! You click it — and you land on another page. Like a portal to another world!"},
    "link": {"ru": "🔗 Ссылка — это волшебная дверь! Нажимаешь — и попадаешь на другую страничку. Как портал в другой мир!",
             "en": "🔗 A link is a magic door! You click it — and you land on another page. Like a portal to another world!"},
    "страница": {"ru": "📄 Веб-страница — это как страничка в книге, только живая! Там можно нажимать кнопки, смотреть видео и читать.",
                 "en": "📄 A web page is like a page in a book, but alive! You can press buttons, watch videos, and read."},
    "page": {"ru": "📄 Веб-страница — это как страничка в книге, только живая! Там можно нажимать кнопки, смотреть видео и читать.",
             "en": "📄 A web page is like a page in a book, but alive! You can press buttons, watch videos, and read."},
    "домен": {"ru": "🏷️ Домен — это имя сайта в интернете! Как адрес дома: google.com — это как сказать 'улица Google, дом 1'.",
              "en": "🏷️ A domain is the name of a website on the internet! Like a house address: google.com is like saying 'Google Street, House 1'."},
    "domain": {"ru": "🏷️ Домен — это имя сайта в интернете! Как адрес дома: google.com — это как сказать 'улица Google, дом 1'.",
               "en": "🏷️ A domain is the name of a website on the internet! Like a house address: google.com is like saying 'Google Street, House 1'."},
    "хостинг": {"ru": "🏠 Хостинг — это место в интернете, где живёт твой сайт. Как квартира, только не для человека, а для страничек!",
                "en": "🏠 Hosting is the place on the internet where your website lives. Like an apartment, but not for a person — for web pages!"},
    "hosting": {"ru": "🏠 Хостинг — это место в интернете, где живёт твой сайт. Как квартира, только не для человека, а для страничек!",
                "en": "🏠 Hosting is the place on the internet where your website lives. Like an apartment, but not for a person — for web pages!"},
    "router": {"ru": "📡 Роутер — это раздатчик интернета! Как водопроводный кран, только вместо воды раздаёт интернет по всему дому.",
               "en": "📡 A router is an internet distributor! Like a water faucet, but instead of water, it distributes internet throughout the house."},
    "роутер": {"ru": "📡 Роутер — это раздатчик интернета! Как водопроводный кран, только вместо воды раздаёт интернет по всему дому.",
               "en": "📡 A router is an internet distributor! Like a water faucet, but instead of water, it distributes internet throughout the house."},
    "бэкенд": {"ru": "🔧 Бэкенд — это то, что работает за кулисами! Как кухня в ресторане: ты не видишь, как готовят, но всё работает. Бэкенд обрабатывает данные, хранит пароли и отвечает на запросы.",
               "en": "🔧 Backend is what works behind the scenes! Like a restaurant kitchen: you don't see the cooking, but everything works. Backend processes data, stores passwords, and handles requests."},
    "backend": {"ru": "🔧 Бэкенд — это то, что работает за кулисами! Как кухня в ресторане: ты не видишь, как готовят, но всё работает. Бэкенд обрабатывает данные, хранит пароли и отвечает на запросы.",
                "en": "🔧 Backend is what works behind the scenes! Like a restaurant kitchen: you don't see the cooking, but everything works. Backend processes data, stores passwords, and handles requests."},
    "сервер": {"ru": "🖥️ Сервер — это мощный компьютер, который работает 24/7! Он хранит сайты, обрабатывает запросы и раздаёт данные. Как библиотекарь, который всегда на работе!",
               "en": "🖥️ A server is a powerful computer that works 24/7! It stores websites, processes requests, and distributes data. Like a librarian who's always on duty!"},
    "server": {"ru": "🖥️ Сервер — это мощный компьютер, который работает 24/7! Он хранит сайты, обрабатывает запросы и раздаёт данные. Как библиотекарь, который всегда на работе!",
               "en": "🖥️ A server is a powerful computer that works 24/7! It stores websites, processes requests, and distributes data. Like a librarian who's always on duty!"},
    "сеть": {"ru": "🕸️ Сеть — это когда компьютеры соединены между собой! Как друзья, которые держатся за руки и обмениваются информацией.",
             "en": "🕸️ A network is when computers are connected to each other! Like friends holding hands and sharing information."},
    "network": {"ru": "🕸️ Сеть — это когда компьютеры соединены между собой! Как друзья, которые держатся за руки и обмениваются информацией.",
                "en": "🕸️ A network is when computers are connected to each other! Like friends holding hands and sharing information."},
    "хост": {"ru": "🏠 Хост — это компьютер в сети, у которого есть свой адрес! Как дом с номером: по этому адресу можно найти нужный компьютер.",
             "en": "🏠 A host is a computer on a network that has its own address! Like a house with a number: you can find the right computer by that address."},
    "host": {"ru": "🏠 Хост — это компьютер в сети, у которого есть свой адрес! Как дом с номером: по этому адресу можно найти нужный компьютер.",
             "en": "🏠 A host is a computer on a network that has its own address! Like a house with a number: you can find the right computer by that address."},
    "клиент": {"ru": "👤 Клиент — это тот, кто просит! Как в кафе: ты — клиент, который заказывает еду. В интернете твой браузер — клиент, который просит данные у сервера.",
               "en": "👤 A client is the one who asks! Like in a cafe: you're the client ordering food. On the internet, your browser is the client asking the server for data."},
    "client": {"ru": "👤 Клиент — это тот, кто просит! Как в кафе: ты — клиент, который заказывает еду. В интернете твой браузер — клиент, который просит данные у сервера.",
               "en": "👤 A client is the one who asks! Like in a cafe: you're the client ordering food. On the internet, your browser is the client asking the server for data."},
    "протокол": {"ru": "📋 Протокол — это правила общения! Как в школе: чтобы задать вопрос, нужно поднять руку. HTTP, TCP/IP — это правила, по которым компьютеры общаются.",
                 "en": "📋 A protocol is a set of communication rules! Like in school: to ask a question, you raise your hand. HTTP, TCP/IP — these are the rules computers follow to communicate."},
    "protocol": {"ru": "📋 Протокол — это правила общения! Как в школе: чтобы задать вопрос, нужно поднять руку. HTTP, TCP/IP — это правила, по которым компьютеры общаются.",
                 "en": "📋 A protocol is a set of communication rules! Like in school: to ask a question, you raise your hand. HTTP, TCP/IP — these are the rules computers follow to communicate."},
    "трафик": {"ru": "🚦 Трафик — это поток данных в интернете! Как машины на дороге: чем больше людей заходят на сайт — тем больше трафик.",
               "en": "🚦 Traffic is the flow of data on the internet! Like cars on a road: the more people visit a website — the more traffic there is."},
    "traffic": {"ru": "🚦 Трафик — это поток данных в интернете! Как машины на дороге: чем больше людей заходят на сайт — тем больше трафик.",
                "en": "🚦 Traffic is the flow of data on the internet! Like cars on a road: the more people visit a website — the more traffic there is."},
    "пинг": {"ru": "🏓 Пинг — это время, за которое сигнал долетает до сервера и обратно! Как эхо: крикнул — и считаешь, когда вернётся. Чем меньше пинг — тем лучше для игр!",
             "en": "🏓 Ping is the time it takes for a signal to reach the server and come back! Like an echo: you shout — and count when it returns. Lower ping is better for gaming!"},
    "ping": {"ru": "🏓 Пинг — это время, за которое сигнал долетает до сервера и обратно! Как эхо: крикнул — и считаешь, когда вернётся. Чем меньше пинг — тем лучше для игр!",
             "en": "🏓 Ping is the time it takes for a signal to reach the server and come back! Like an echo: you shout — and count when it returns. Lower ping is better for gaming!"},
    "прокси": {"ru": "🎭 Прокси — это посредник! Как если бы ты просил друга купить тебе что-то, вместо того чтобы идти самому. Прокси скрывает твой адрес и может ускорять доступ.",
               "en": "🎭 A proxy is a middleman! Like asking a friend to buy something for you instead of going yourself. A proxy hides your address and can speed up access."},
    "proxy": {"ru": "🎭 Прокси — это посредник! Как если бы ты просил друга купить тебе что-то, вместо того чтобы идти самому. Прокси скрывает твой адрес и может ускорять доступ.",
              "en": "🎭 A proxy is a middleman! Like asking a friend to buy something for you instead of going yourself. A proxy hides your address and can speed up access."},
    "теги": {"ru": "🏷️ Теги — это метки или ярлыки! Как стикеры на папках: они помогают найти нужное. На сайте теги говорят браузеру: 'это заголовок', 'это картинка'.",
             "en": "🏷️ Tags are labels or stickers! Like sticky notes on folders: they help you find what you need. On a website, tags tell the browser: 'this is a heading', 'this is an image'."},
    "tags": {"ru": "🏷️ Теги — это метки или ярлыки! Как стикеры на папках: они помогают найти нужное. На сайте теги говорят браузеру: 'это заголовок', 'это картинка'.",
             "en": "🏷️ Tags are labels or stickers! Like sticky notes on folders: they help you find what you need. On a website, tags tell the browser: 'this is a heading', 'this is an image'."},

    # === Programming & Data / Программирование и данные ===
    "программирование": {"ru": "⌨️ Программирование — это когда ты пишешь записку компьютеру на специальном языке, а компьютер её понимает и делает то, что ты хочешь. Как заклинание, только для машины!",
                         "en": "⌨️ Programming is when you write a note to a computer in a special language, and the computer understands it and does what you want. Like a spell, but for machines!"},
    "programming": {"ru": "⌨️ Программирование — это когда ты пишешь записку компьютеру на специальном языке, а компьютер её понимает и делает то, что ты хочешь. Как заклинание, только для машины!",
                    "en": "⌨️ Programming is when you write a note to a computer in a special language, and the computer understands it and does what you want. Like a spell, but for machines!"},
    "код": {"ru": "💡 Код — это специальные команды, которые говорят компьютеру что делать. Как если бы ты писал записки роботу, а робот их выполнял!",
            "en": "💡 Code is special commands that tell a computer what to do. Like writing notes to a robot, and the robot follows them!"},
    "code": {"ru": "💡 Код — это специальные команды, которые говорят компьютеру что делать. Как если бы ты писал записки роботу, а робот их выполнял!",
             "en": "💡 Code is special commands that tell a computer what to do. Like writing notes to a robot, and the robot follows them!"},
    "алгоритм": {"ru": "📝 Алгоритм — это как рецепт! Представь, что ты делаешь бутерброд: сначала хлеб, потом масло, потом сыр. Алгоритм — это пошаговая инструкция для компьютера.",
                 "en": "📝 An algorithm is like a recipe! Imagine making a sandwich: first bread, then butter, then cheese. An algorithm is a step-by-step instruction for a computer."},
    "algorithm": {"ru": "📝 Алгоритм — это как рецепт! Представь, что ты делаешь бутерброд: сначала хлеб, потом масло, потом сыр. Алгоритм — это пошаговая инструкция для компьютера.",
                  "en": "📝 An algorithm is like a recipe! Imagine making a sandwich: first bread, then butter, then cheese. An algorithm is a step-by-step instruction for a computer."},
    "база данных": {"ru": "📦 База данных — это как большой шкаф с ящиками, где всё разложено по полочкам. Компьютер кладёт туда информацию и быстро находит, когда нужно.",
                    "en": "📦 A database is like a big cabinet with drawers, where everything is organized on shelves. The computer puts information there and finds it quickly when needed."},
    "database": {"ru": "📦 База данных — это как большой шкаф с ящиками, где всё разложено по полочкам. Компьютер кладёт туда информацию и быстро находит, когда нужно.",
                 "en": "📦 A database is like a big cabinet with drawers, where everything is organized on shelves. The computer puts information there and finds it quickly when needed."},
    "файл": {"ru": "📄 Файл — это как листок бумаги внутри компьютера. На нём может быть текст, картинка или музыка. Компьютер хранит файлы в папках, как мы — документы в портфеле.",
             "en": "📄 A file is like a sheet of paper inside a computer. It can have text, an image, or music. The computer stores files in folders, like we store documents in a briefcase."},
    "file": {"ru": "📄 Файл — это как листок бумаги внутри компьютера. На нём может быть текст, картинка или музыка. Компьютер хранит файлы в папках, как мы — документы в портфеле.",
             "en": "📄 A file is like a sheet of paper inside a computer. It can have text, an image, or music. The computer stores files in folders, like we store documents in a briefcase."},
    "пароль": {"ru": "🔑 Пароль — это секретное слово, как дверь в тайную комнату! Только тот, кто знает слово, может войти.",
               "en": "🔑 A password is a secret word, like a door to a secret room! Only the one who knows the word can enter."},
    "password": {"ru": "🔑 Пароль — это секретное слово, как дверь в тайную комнату! Только тот, кто знает слово, может войти.",
                 "en": "🔑 A password is a secret word, like a door to a secret room! Only the one who knows the word can enter."},
    "переменная": {"ru": "📦 Переменная — это коробочка с названием, в которой компьютер хранит числа, слова и другие вещи. Как банка с подписью 'конфеты'!",
                   "en": "📦 A variable is a labeled box where the computer stores numbers, words, and other things. Like a jar labeled 'candy'!"},
    "variable": {"ru": "📦 Переменная — это коробочка с названием, в которой компьютер хранит числа, слова и другие вещи. Как банка с подписью 'конфеты'!",
                 "en": "📦 A variable is a labeled box where the computer stores numbers, words, and other things. Like a jar labeled 'candy'!"},
    "функция": {"ru": "🎯 Функция — это мини-рецепт внутри программы! Один раз написал — и можешь использовать сколько хочешь. Как мультипекарь: положил тесто — получил пирожок!",
                "en": "🎯 A function is a mini-recipe inside a program! Write it once — and use it as many times as you want. Like a bakery machine: put in dough — get a pie!"},
    "function": {"ru": "🎯 Функция — это мини-рецепт внутри программы! Один раз написал — и можешь использовать сколько хочешь. Как мультипекарь: положил тесто — получил пирожок!",
                 "en": "🎯 A function is a mini-recipe inside a program! Write it once — and use it as many times as you want. Like a bakery machine: put in dough — get a pie!"},
    "цикл": {"ru": "🔄 Цикл — это когда компьютер повторяет одно и то же много раз. Как если бы ты сказал: 'пока не устану — бегай по кругу!'",
             "en": "🔄 A loop is when a computer repeats the same thing over and over. Like saying: 'keep running in circles until you're tired!'"},
    "loop": {"ru": "🔄 Цикл — это когда компьютер повторяет одно и то же много раз. Как если бы ты сказал: 'пока не устану — бегай по кругу!'",
             "en": "🔄 A loop is when a computer repeats the same thing over and over. Like saying: 'keep running in circles until you're tired!'"},
    "баг": {"ru": "🐛 Баг — это ошибка в программе! Как если бы в рецепте торта перепутали соль и сахар — и всё пошло не так.",
            "en": "🐛 A bug is an error in a program! Like mixing up salt and sugar in a cake recipe — and everything goes wrong."},
    "bug": {"ru": "🐛 Баг — это ошибка в программе! Как если бы в рецепте торта перепутали соль и сахар — и всё пошло не так.",
            "en": "🐛 A bug is an error in a program! Like mixing up salt and sugar in a cake recipe — and everything goes wrong."},
    "отладка": {"ru": "🔧 Отладка — это когда программист ищет и чинит ошибки в коде. Как детектив, который разгадывает загадки!",
                "en": "🔧 Debugging is when a programmer finds and fixes errors in code. Like a detective solving puzzles!"},
    "debugging": {"ru": "🔧 Отладка — это когда программист ищет и чинит ошибки в коде. Как детектив, который разгадывает загадки!",
                  "en": "🔧 Debugging is when a programmer finds and fixes errors in code. Like a detective solving puzzles!"},
    "интерфейс": {"ru": "🎨 Интерфейс — это всё, что ты видишь на экране и можешь потрогать! Кнопки, меню, картинки — это как пульт управления программой.",
                  "en": "🎨 An interface is everything you see on screen and can interact with! Buttons, menus, images — it's like a control panel for a program."},
    "interface": {"ru": "🎨 Интерфейс — это всё, что ты видишь на экране и можешь потрогать! Кнопки, меню, картинки — это как пульт управления программой.",
                  "en": "🎨 An interface is everything you see on screen and can interact with! Buttons, menus, images — it's like a control panel for a program."},
    "api": {"ru": "🔌 API — это как меню в ресторане! Ты говоришь официанту что хочешь, а кухня готовит. API — это способ программ просить друг друга о помощи.",
            "en": "🔌 API is like a restaurant menu! You tell the waiter what you want, and the kitchen prepares it. API is how programs ask each other for help."},
    "git": {"ru": "📚 Git — это машина времени для программиста! Он запоминает все изменения и позволяет вернуться назад, если что-то сломал.",
            "en": "📚 Git is a time machine for programmers! It remembers all changes and lets you go back if something breaks."},
    "python": {"ru": "🐍 Python — это язык программирования, который похож на обычный английский! Один из самых лёгких для новичков.",
               "en": "🐍 Python is a programming language that looks like plain English! One of the easiest for beginners."},
    "питон": {"ru": "🐍 Python — это язык программирования, который похож на обычный английский! Один из самых лёгких для новичков.",
              "en": "🐍 Python is a programming language that looks like plain English! One of the easiest for beginners."},
    "javascript": {"ru": "🌟 JavaScript — это язык, который оживляет сайты! Благодаря ему кнопки нажимаются, анимации двигаются, а формы проверяются.",
                   "en": "🌟 JavaScript is the language that brings websites to life! Thanks to it, buttons click, animations move, and forms validate."},
    "html": {"ru": "🏗️ HTML — это скелет любого сайта! Он говорит браузеру: 'здесь будет заголовок, здесь картинка, а здесь кнопка'.",
             "en": "🏗️ HTML is the skeleton of any website! It tells the browser: 'here goes a heading, here an image, and here a button'."},
    "css": {"ru": "🎨 CSS — это одежда для сайта! Он говорит: 'эта надпись будет красная, эта кнопка круглая, а этот фон голубой'.",
            "en": "🎨 CSS is the clothing for a website! It says: 'this text will be red, this button round, and this background blue'."},
    "массив": {"ru": "📊 Массив — это как ряд ячеек в шкафу! Каждая ячейка имеет номер, и в каждой можно что-то хранить.",
               "en": "📊 An array is like a row of lockers! Each locker has a number, and you can store something in each."},
    "array": {"ru": "📊 Массив — это как ряд ячеек в шкафу! Каждая ячейка имеет номер, и в каждой можно что-то хранить.",
              "en": "📊 An array is like a row of lockers! Each locker has a number, and you can store something in each."},
    "строка": {"ru": "📝 Строка — это текст, который компьютер понимает как одну фразу. Даже если там сто слов — для компьютера это одна строка!",
               "en": "📝 A string is text that a computer treats as one phrase. Even if it's a hundred words — to the computer, it's one string!"},
    "string": {"ru": "📝 Строка — это текст, который компьютер понимает как одну фразу. Даже если там сто слов — для компьютера это одна строка!",
               "en": "📝 A string is text that a computer treats as one phrase. Even if it's a hundred words — to the computer, it's one string!"},
    "число": {"ru": "🔢 Число — это то, с чем компьютер умеет работать! Складывать, умножать, делить — он считает быстрее любого калькулятора.",
              "en": "🔢 A number is what a computer knows how to work with! Add, multiply, divide — it calculates faster than any calculator."},
    "number": {"ru": "🔢 Число — это то, с чем компьютер умеет работать! Складывать, умножать, делить — он считает быстрее любого калькулятора.",
               "en": "🔢 A number is what a computer knows how to work with! Add, multiply, divide — it calculates faster than any calculator."},
    "boolean": {"ru": "✅ Булево значение — это просто 'да' или 'нет', 'правда' или 'ложь'. Компьютер использует это чтобы принимать решения.",
                "en": "✅ A boolean is simply 'yes' or 'no', 'true' or 'false'. A computer uses this to make decisions."},
    "булево": {"ru": "✅ Булево значение — это просто 'да' или 'нет', 'правда' или 'ложь'. Компьютер использует это чтобы принимать решения.",
               "en": "✅ A boolean is simply 'yes' or 'no', 'true' or 'false'. A computer uses this to make decisions."},
    "архитектура": {"ru": "🏗️ Архитектура — это план здания! Только не для дома, а для программы. Она говорит, из каких частей состоит приложение и как они общаются.",
                    "en": "🏗️ Architecture is a building plan! But not for a house — for a program. It says what parts an app consists of and how they communicate."},
    "architecture": {"ru": "🏗️ Архитектура — это план здания! Только не для дома, а для программы. Она говорит, из каких частей состоит приложение и как они общаются.",
                     "en": "🏗️ Architecture is a building plan! But not for a house — for a program. It says what parts an app consists of and how they communicate."},
    "безопасность": {"ru": "🛡️ Безопасность — это защита от плохих ребят! Как замок на двери, только для компьютера. Пароли, шифрование — всё это часть безопасности.",
                     "en": "🛡️ Security is protection from bad guys! Like a lock on a door, but for a computer. Passwords, encryption — all part of security."},
    "security": {"ru": "🛡️ Безопасность — это защита от плохих ребят! Как замок на двери, только для компьютера. Пароли, шифрование — всё это часть безопасности.",
                 "en": "🛡️ Security is protection from bad guys! Like a lock on a door, but for a computer. Passwords, encryption — all part of security."},
    "бета-версия": {"ru": "🧪 Бета-версия — это тестовая версия программы! Как дегустация нового блюда: ещё не идеально, но уже можно попробовать и дать советы.",
                    "en": "🧪 A beta version is a test version of a program! Like tasting a new dish: not perfect yet, but you can try it and give feedback."},
    "beta": {"ru": "🧪 Бета-версия — это тестовая версия программы! Как дегустация нового блюда: ещё не идеально, но уже можно попробовать и дать советы.",
             "en": "🧪 A beta version is a test version of a program! Like tasting a new dish: not perfect yet, but you can try it and give feedback."},
    "библиотека": {"ru": "📚 Библиотека — это набор готовых инструментов! Как если бы тебе дали готовый набор для рисования вместо того, чтобы делать кисточки самому.",
                   "en": "📚 A library is a set of ready-made tools! Like being given a ready-made art kit instead of making brushes yourself."},
    "library": {"ru": "📚 Библиотека — это набор готовых инструментов! Как если бы тебе дали готовый набор для рисования вместо того, чтобы делать кисточки самому.",
                "en": "📚 A library is a set of ready-made tools! Like being given a ready-made art kit instead of making brushes yourself."},
    "вход": {"ru": "⬅️ Вход (Input) — это то, что ты даёшь компьютеру! Нажал кнопку, ввёл текст, щёлкнул мышкой — всё это вход.",
             "en": "⬅️ Input is what you give to a computer! Pressed a button, typed text, clicked a mouse — all of that is input."},
    "input": {"ru": "⬅️ Вход (Input) — это то, что ты даёшь компьютеру! Нажал кнопку, ввёл текст, щёлкнул мышкой — всё это вход.",
              "en": "⬅️ Input is what you give to a computer! Pressed a button, typed text, clicked a mouse — all of that is input."},
    "вывод": {"ru": "➡️ Вывод (Output) — это то, что компьютер показывает тебе! Картинка на экране, звук из динамиков, распечатанный текст — всё это вывод.",
              "en": "➡️ Output is what a computer shows you! An image on screen, sound from speakers, printed text — all of that is output."},
    "output": {"ru": "➡️ Вывод (Output) — это то, что компьютер показывает тебе! Картинка на экране, звук из динамиков, распечатанный текст — всё это вывод.",
               "en": "➡️ Output is what a computer shows you! An image on screen, sound from speakers, printed text — all of that is output."},
    "виртуализация": {"ru": "🎭 Виртуализация — это когда один компьютер притворяется несколькими! Как если бы из одной квартиры сделали несколько маленьких студий.",
                      "en": "🎭 Virtualization is when one computer pretends to be several! Like turning one apartment into several small studios."},
    "virtualization": {"ru": "🎭 Виртуализация — это когда один компьютер притворяется несколькими! Как если бы из одной квартиры сделали несколько маленьких студий.",
                       "en": "🎭 Virtualization is when one computer pretends to be several! Like turning one apartment into several small studios."},
    "запрос": {"ru": "📩 Запрос — это когда программа просит что-то! Как если бы ты написал записку: 'дай мне информацию про погоду'. Компьютер отвечает.",
               "en": "📩 A request is when a program asks for something! Like writing a note: 'give me weather info'. The computer responds."},
    "request": {"ru": "📩 Запрос — это когда программа просит что-то! Как если бы ты написал записку: 'дай мне информацию про погоду'. Компьютер отвечает.",
                "en": "📩 A request is when a program asks for something! Like writing a note: 'give me weather info'. The computer responds."},
    "query": {"ru": "📩 Запрос — это когда программа просит что-то! Как если бы ты написал записку: 'дай мне информацию про погоду'. Компьютер отвечает.",
              "en": "📩 A query is when a program asks for something! Like writing a note: 'give me weather info'. The computer responds."},
    "защита": {"ru": "🔒 Защита — это всё, что охраняет твои данные! Пароли, антивирусы, шифрование — как забор, камера и сейф для компьютера.",
               "en": "🔒 Protection is everything that guards your data! Passwords, antivirus, encryption — like a fence, camera, and safe for a computer."},
    "идентификация": {"ru": "🆔 Идентификация — это когда компьютер узнаёт кто ты! Как паспорт: 'я — Вася, вот мой номер'. Логин, отпечаток пальца, лицо — это идентификация.",
                      "en": "🆔 Identification is when a computer figures out who you are! Like a passport: 'I'm Vasya, here's my number'. Login, fingerprint, face — that's identification."},
    "identification": {"ru": "🆔 Идентификация — это когда компьютер узнаёт кто ты! Как паспорт: 'я — Вася, вот мой номер'. Логин, отпечаток пальца, лицо — это идентификация.",
                       "en": "🆔 Identification is when a computer figures out who you are! Like a passport: 'I'm Vasya, here's my number'. Login, fingerprint, face — that's identification."},
    "инфраструктура": {"ru": "🏗️ Инфраструктура — это всё, что нужно для работы! Серверы, сети, базы данных — как дороги, мосты и трубы для города. Без неё ничего не работает.",
                       "en": "🏗️ Infrastructure is everything needed for things to work! Servers, networks, databases — like roads, bridges, and pipes for a city. Without it, nothing works."},
    "infrastructure": {"ru": "🏗️ Инфраструктура — это всё, что нужно для работы! Серверы, сети, базы данных — как дороги, мосты и трубы для города. Без неё ничего не работает.",
                       "en": "🏗️ Infrastructure is everything needed for things to work! Servers, networks, databases — like roads, bridges, and pipes for a city. Without it, nothing works."},
    "искусственный интеллект": {"ru": "🧠 Искусственный интеллект — это как если бы компьютер научился думать сам! Представь, что твой планшет умеет угадывать, какие мультики тебе нравятся, и сам их включает.",
                                "en": "🧠 Artificial Intelligence is like a computer learning to think on its own! Imagine your tablet guessing which cartoons you like and playing them automatically."},
    "ai": {"ru": "🧠 Искусственный интеллект — это как если бы компьютер научился думать сам! Представь, что твой планшет умеет угадывать, какие мультики тебе нравятся, и сам их включает.",
           "en": "🧠 Artificial Intelligence is like a computer learning to think on its own! Imagine your tablet guessing which cartoons you like and playing them automatically."},
    "итерация": {"ru": "🔄 Итерация — это один шаг из множества! Как один удар в барабан в длинной песне. В программировании итерация — это один повтор цикла.",
                 "en": "🔄 An iteration is one step out of many! Like one drum beat in a long song. In programming, an iteration is one repeat of a loop."},
    "iteration": {"ru": "🔄 Итерация — это один шаг из множества! Как один удар в барабан в длинной песне. В программировании итерация — это один повтор цикла.",
                  "en": "🔄 An iteration is one step out of many! Like one drum beat in a long song. In programming, an iteration is one repeat of a loop."},
    "кеш": {"ru": "⚡ Кеш — это быстрая память-подручная! Как записная книжка на столе: туда кладут то, что нужно прямо сейчас, чтобы не бегать к шкафу.",
            "en": "⚡ Cache is fast helper memory! Like a notepad on your desk: you put what you need right now there, so you don't have to run to the cabinet."},
    "cache": {"ru": "⚡ Кеш — это быстрая память-подручная! Как записная книжка на столе: туда кладут то, что нужно прямо сейчас, чтобы не бегать к шкафу.",
              "en": "⚡ Cache is fast helper memory! Like a notepad on your desk: you put what you need right now there, so you don't have to run to the cabinet."},
    "класс": {"ru": "🏷️ Класс — это чертёж для создания объектов! Как рецепт торта: один рецепт — много одинаковых тортов. В программировании класс создаёт объекты.",
              "en": "🏷️ A class is a blueprint for creating objects! Like a cake recipe: one recipe — many identical cakes. In programming, a class creates objects."},
    "class": {"ru": "🏷️ Класс — это чертёж для создания объектов! Как рецепт торта: один рецепт — много одинаковых тортов. В программировании класс создаёт объекты.",
              "en": "🏷️ A class is a blueprint for creating objects! Like a cake recipe: one recipe — many identical cakes. In programming, a class creates objects."},
    "кластер": {"ru": "🖥️ Кластер — это группа компьютеров, работающих вместе! Как команда супергероев: каждый силён по-своему, а вместе — непобедимы.",
                "en": "🖥️ A cluster is a group of computers working together! Like a team of superheroes: each is strong in their own way, but together — invincible."},
    "cluster": {"ru": "🖥️ Кластер — это группа компьютеров, работающих вместе! Как команда супергероев: каждый силён по-своему, а вместе — непобедимы.",
                "en": "🖥️ A cluster is a group of computers working together! Like a team of superheroes: each is strong in their own way, but together — invincible."},
    "компилятор": {"ru": "🔀 Компилятор — это переводчик! Он берёт код, который написал программист, и переводит его на язык, который понимает компьютер.",
                   "en": "🔀 A compiler is a translator! It takes the code a programmer wrote and translates it into a language the computer understands."},
    "compiler": {"ru": "🔀 Компилятор — это переводчик! Он берёт код, который написал программист, и переводит его на язык, который понимает компьютер.",
                 "en": "🔀 A compiler is a translator! It takes the code a programmer wrote and translates it into a language the computer understands."},
    "компонент": {"ru": "🧩 Компонент — это деталь-кирпичик! Как кубик LEGO: сам по себе простой, но из них можно собрать что угодно. В программах компоненты — это части интерфейса.",
                  "en": "🧩 A component is a building block! Like a LEGO brick: simple on its own, but you can build anything from them. In programs, components are parts of the interface."},
    "component": {"ru": "🧩 Компонент — это деталь-кирпичик! Как кубик LEGO: сам по себе простой, но из них можно собрать что угодно. В программах компоненты — это части интерфейса.",
                  "en": "🧩 A component is a building block! Like a LEGO brick: simple on its own, but you can build anything from them. In programs, components are parts of the interface."},
    "контейнер": {"ru": "📦 Контейнер — это упакованная программа со всем, что ей нужно! Как чемодан: положил вещи — и можно везти куда угодно. Docker — самый популярный контейнер.",
                  "en": "📦 A container is a packaged program with everything it needs! Like a suitcase: pack your stuff — and you can take it anywhere. Docker is the most popular container."},
    "container": {"ru": "📦 Контейнер — это упакованная программа со всем, что ей нужно! Как чемодан: положил вещи — и можно везти куда угодно. Docker — самый популярный контейнер.",
                  "en": "📦 A container is a packaged program with everything it needs! Like a suitcase: pack your stuff — and you can take it anywhere. Docker is the most popular container."},
    "конфигурация": {"ru": "⚙️ Конфигурация — это настройки! Как если бы ты настроил сиденье и зеркала в машине под себя. Программа тоже любит персонализацию.",
                     "en": "⚙️ Configuration is settings! Like adjusting the seat and mirrors in a car to fit you. Programs like personalization too."},
    "configuration": {"ru": "⚙️ Конфигурация — это настройки! Как если бы ты настроил сиденье и зеркала в машине под себя. Программа тоже любит персонализацию.",
                      "en": "⚙️ Configuration is settings! Like adjusting the seat and mirrors in a car to fit you. Programs like personalization too."},
    "криптография": {"ru": "🔐 Криптография — это наука о шифрах! Как секретный язык, который знают только свои. Даже если кто-то перехватит сообщение — не сможет прочитать.",
                     "en": "🔐 Cryptography is the science of codes! Like a secret language only insiders know. Even if someone intercepts a message — they can't read it."},
    "cryptography": {"ru": "🔐 Криптография — это наука о шифрах! Как секретный язык, который знают только свои. Даже если кто-то перехватит сообщение — не сможет прочитать.",
                     "en": "🔐 Cryptography is the science of codes! Like a secret language only insiders know. Even if someone intercepts a message — they can't read it."},
    "лог": {"ru": "📋 Лог — это дневник программы! Она записывает всё, что делает: 'запустилась', 'получила запрос', 'ошибка'. Как бортовой журнал корабля.",
            "en": "📋 A log is a program's diary! It records everything it does: 'started', 'received request', 'error'. Like a ship's logbook."},
    "log": {"ru": "📋 Лог — это дневник программы! Она записывает всё, что делает: 'запустилась', 'получила запрос', 'ошибка'. Как бортовой журнал корабля.",
            "en": "📋 A log is a program's diary! It records everything it does: 'started', 'received request', 'error'. Like a ship's logbook."},
    "дебаггинг": {"ru": "🐛 Дебаггинг — это охота на баги! Как когда ты ищешь, почему игрушка не работает, и чинишь её. Программист ищет ошибки в коде и исправляет.",
                  "en": "🐛 Debugging is a bug hunt! Like figuring out why a toy doesn't work and fixing it. A programmer finds errors in code and fixes them."},
    "деплой": {"ru": "🚀 Деплой — это когда программу выкладывают в интернет! Как если бы ты испёк торт и поставил его на витрину — теперь все могут попробовать.",
               "en": "🚀 Deploy is when you put a program on the internet! Like baking a cake and putting it on display — now everyone can try it."},
    "deploy": {"ru": "🚀 Деплой — это когда программу выкладывают в интернет! Как если бы ты испёк торт и поставил его на витрину — теперь все могут попробовать.",
               "en": "🚀 Deploy is when you put a program on the internet! Like baking a cake and putting it on display — now everyone can try it."},
    "джейсон": {"ru": "📋 JSON — это формат записи данных! Как если бы ты написал: '{\"имя\": \"Вася\", \"возраст\": 10}'. Компьютеры обожают такой формат — он простой и понятный.",
                "en": "📋 JSON is a data format! Like writing: '{\"name\": \"Vasya\", \"age\": 10}'. Computers love this format — it's simple and clear."},
    "json": {"ru": "📋 JSON — это формат записи данных! Как если бы ты написал: '{\"name\": \"Vasya\", \"age\": 10}'. Компьютеры обожают такой формат — он простой и понятный.",
             "en": "📋 JSON is a data format! Like writing: '{\"name\": \"Vasya\", \"age\": 10}'. Computers love this format — it's simple and clear."},
    "машинное обучение": {"ru": "🤖 Машинное обучение — это когда компьютер учится на примерах! Как ребёнок: показал ему сто картинок с котами — и он научился их узнавать.",
                         "en": "🤖 Machine learning is when a computer learns from examples! Like a child: show it a hundred cat pictures — and it learns to recognize them."},
    "ml": {"ru": "🤖 Машинное обучение — это когда компьютер учится на примерах! Как ребёнок: показал ему сто картинок с котами — и он научился их узнавать.",
           "en": "🤖 Machine learning is when a computer learns from examples! Like a child: show it a hundred cat pictures — and it learns to recognize them."},
    "machine learning": {"ru": "🤖 Машинное обучение — это когда компьютер учится на примерах! Как ребёнок: показал ему сто картинок с котами — и он научился их узнавать.",
                         "en": "🤖 Machine learning is when a computer learns from examples! Like a child: show it a hundred cat pictures — and it learns to recognize them."},
    "микросервис": {"ru": "🧩 Микросервис — это маленькая самостоятельная часть большой программы! Как отделы в магазине: один занимается оплатой, другой — доставкой. Каждый делает своё дело.",
                    "en": "🧩 A microservice is a small independent part of a big program! Like departments in a store: one handles payment, another — delivery. Each does its own job."},
    "microservice": {"ru": "🧩 Микросервис — это маленькая самостоятельная часть большой программы! Как отделы в магазине: один занимается оплатой, другой — доставкой. Каждый делает своё дело.",
                     "en": "🧩 A microservice is a small independent part of a big program! Like departments in a store: one handles payment, another — delivery. Each does its own job."},
    "модуль": {"ru": "📦 Модуль — это отдельная часть программы! Как ящик в комоде: в одном одежда, в другом носки. Модули помогают не запутаться в коде.",
               "en": "📦 A module is a separate part of a program! Like a drawer in a dresser: one has clothes, another has socks. Modules help keep code organized."},
    "module": {"ru": "📦 Модуль — это отдельная часть программы! Как ящик в комоде: в одном одежда, в другом носки. Модули помогают не запутаться в коде.",
               "en": "📦 A module is a separate part of a program! Like a drawer in a dresser: one has clothes, another has socks. Modules help keep code organized."},
    "мониторинг": {"ru": "👁️ Мониторинг — это слежение за здоровьем программы! Как если бы врач следил за пульсом и температурой. Если что-то не так — сразу видно!",
                   "en": "👁️ Monitoring is watching a program's health! Like a doctor checking pulse and temperature. If something's wrong — you see it right away!"},
    "monitoring": {"ru": "👁️ Мониторинг — это слежение за здоровьем программы! Как если бы врач следил за пульсом и температурой. Если что-то не так — сразу видно!",
                   "en": "👁️ Monitoring is watching a program's health! Like a doctor checking pulse and temperature. If something's wrong — you see it right away!"},
    "нейросеть": {"ru": "🧬 Нейросеть — это компьютерный мозг! Она умеет распознавать лица, переводить тексты и даже рисовать!",
                  "en": "🧬 A neural network is a computer brain! It can recognize faces, translate texts, and even draw!"},
    "neural network": {"ru": "🧬 Нейросеть — это компьютерный мозг! Она умеет распознавать лица, переводить тексты и даже рисовать!",
                       "en": "🧬 A neural network is a computer brain! It can recognize faces, translate texts, and even draw!"},
    "обновление": {"ru": "🔄 Обновление — это когда программа становится лучше! Как когда ты растёшь и учишься новому, только для компьютера.",
                   "en": "🔄 An update is when a program gets better! Like when you grow and learn new things, but for a computer."},
    "update": {"ru": "🔄 Обновление — это когда программа становится лучше! Как когда ты растёшь и учишься новому, только для компьютера.",
               "en": "🔄 An update is when a program gets better! Like when you grow and learn new things, but for a computer."},
    "обработка данных": {"ru": "⚙️ Обработка данных — это когда компьютер берёт сырые данные и делает из них что-то полезное! Как если бы ты взял ингредиенты и приготовил суп.",
                         "en": "⚙️ Data processing is when a computer takes raw data and makes something useful from it! Like taking ingredients and cooking soup."},
    "data processing": {"ru": "⚙️ Обработка данных — это когда компьютер берёт сырые данные и делает из них что-то полезное! Как если бы ты взял ингредиенты и приготовил суп.",
                        "en": "⚙️ Data processing is when a computer takes raw data and makes something useful from it! Like taking ingredients and cooking soup."},
    "объект": {"ru": "📦 Объект — это вещь в программе! У неё есть свойства (цвет, размер) и действия (бежать, прыгать). Как персонаж в игре.",
               "en": "📦 An object is a thing in a program! It has properties (color, size) and actions (run, jump). Like a character in a game."},
    "object": {"ru": "📦 Объект — это вещь в программе! У неё есть свойства (цвет, размер) и действия (бежать, прыгать). Как персонаж в игре.",
               "en": "📦 An object is a thing in a program! It has properties (color, size) and actions (run, jump). Like a character in a game."},
    "окно": {"ru": "🪟 Окно — это прямоугольная область на экране! Как рамка для картины: внутри — программа, документ или игра.",
             "en": "🪟 A window is a rectangular area on screen! Like a picture frame: inside is a program, document, or game."},
    "window": {"ru": "🪟 Окно — это прямоугольная область на экране! Как рамка для картины: внутри — программа, документ или игра.",
               "en": "🪟 A window is a rectangular area on screen! Like a picture frame: inside is a program, document, or game."},
    "оптимизация": {"ru": "🏎️ Оптимизация — это когда программу ускоряют и улучшают! Как тюнинг автомобиля: убирают лишнее, добавляют мощности.",
                    "en": "🏎️ Optimization is when you speed up and improve a program! Like tuning a car: remove the unnecessary, add power."},
    "optimization": {"ru": "🏎️ Оптимизация — это когда программу ускоряют и улучшают! Как тюнинг автомобиля: убирают лишнее, добавляют мощности.",
                     "en": "🏎️ Optimization is when you speed up and improve a program! Like tuning a car: remove the unnecessary, add power."},
    "ошибка": {"ru": "❌ Ошибка — это когда что-то пошло не так! Как если бы ты хотел открыть дверь, а открыл шкаф. В программах ошибки бывают разные — и их нужно исправлять.",
               "en": "❌ An error is when something goes wrong! Like trying to open a door but opening a closet instead. Programs have different kinds of errors — and they need fixing."},
    "error": {"ru": "❌ Ошибка — это когда что-то пошло не так! Как если бы ты хотел открыть дверь, а открыл шкаф. В программах ошибки бывают разные — и их нужно исправлять.",
              "en": "❌ An error is when something goes wrong! Like trying to open a door but opening a closet instead. Programs have different kinds of errors — and they need fixing."},
    "пакет": {"ru": "📦 Пакет — это набор готовых инструментов для программиста! Как набор Lego: открыл коробку — и у тебя есть всё, чтобы построить что-то.",
              "en": "📦 A package is a set of ready-made tools for a programmer! Like a Lego set: open the box — and you have everything to build something."},
    "package": {"ru": "📦 Пакет — это набор готовых инструментов для программиста! Как набор Lego: открыл коробку — и у тебя есть всё, чтобы построить что-то.",
                "en": "📦 A package is a set of ready-made tools for a programmer! Like a Lego set: open the box — and you have everything to build something."},
    "песочница": {"ru": "🏖️ Песочница — это безопасное место для тестов! Как детская песочница: что бы ты там ни строил — снаружи ничего не сломается. Программисты тестируют код в песочнице.",
                  "en": "🏖️ A sandbox is a safe place for testing! Like a kids' sandbox: whatever you build there — nothing breaks outside. Programmers test code in a sandbox."},
    "sandbox": {"ru": "🏖️ Песочница — это безопасное место для тестов! Как детская песочница: что бы ты там ни строил — снаружи ничего не сломается. Программисты тестируют код в песочнице.",
                "en": "🏖️ A sandbox is a safe place for testing! Like a kids' sandbox: whatever you build there — nothing breaks outside. Programmers test code in a sandbox."},
    "плагин": {"ru": "🔌 Плагин — это маленькое дополнение! Как DLC в игре: основная игра работает, а плагин добавляет новые возможности.",
               "en": "🔌 A plugin is a small add-on! Like DLC in a game: the main game works, and the plugin adds new features."},
    "plugin": {"ru": "🔌 Плагин — это маленькое дополнение! Как DLC в игре: основная игра работает, а плагин добавляет новые возможности.",
               "en": "🔌 A plugin is a small add-on! Like DLC in a game: the main game works, and the plugin adds new features."},
    "платформа": {"ru": "🏗️ Платформа — это основа, на которой строят! Как фундамент дома. Android, iOS, Windows — это платформы, на которых работают приложения.",
                  "en": "🏗️ A platform is the foundation you build on! Like a house foundation. Android, iOS, Windows — these are platforms that apps run on."},
    "platform": {"ru": "🏗️ Платформа — это основа, на которой строят! Как фундамент дома. Android, iOS, Windows — это платформы, на которых работают приложения.",
                 "en": "🏗️ A platform is the foundation you build on! Like a house foundation. Android, iOS, Windows — these are platforms that apps run on."},
    "поток": {"ru": "🧵 Поток — это отдельная задача внутри программы! Как если бы ты одновременно слушал музыку и писал сообщение — два потока в голове.",
              "en": "🧵 A thread is a separate task inside a program! Like listening to music and writing a message at the same time — two threads in your head."},
    "thread": {"ru": "🧵 Поток — это отдельная задача внутри программы! Как если бы ты одновременно слушал музыку и писал сообщение — два потока в голове.",
               "en": "🧵 A thread is a separate task inside a program! Like listening to music and writing a message at the same time — two threads in your head."},
    "проект": {"ru": "📂 Проект — это всё, что связано с одной задачей! Как папка в школе: все тетради, чертежи и заметки по одному предмету.",
               "en": "📂 A project is everything related to one task! Like a school folder: all notebooks, drawings, and notes for one subject."},
    "project": {"ru": "📂 Проект — это всё, что связано с одной задачей! Как папка в школе: все тетради, чертежи и заметки по одному предмету.",
                "en": "📂 A project is everything related to one task! Like a school folder: all notebooks, drawings, and notes for one subject."},
    "процесс": {"ru": "⚡ Процесс — это запущенная программа! Как если бы ты включил чайник — он стал 'процессом'. Компьютер может делать много процессов одновременно.",
                "en": "⚡ A process is a running program! Like turning on a kettle — it becomes a 'process'. A computer can run many processes at once."},
    "process": {"ru": "⚡ Процесс — это запущенная программа! Как если бы ты включил чайник — он стал 'процессом'. Компьютер может делать много процессов одновременно.",
                "en": "⚡ A process is a running program! Like turning on a kettle — it becomes a 'process'. A computer can run many processes at once."},
    "развертывание": {"ru": "🚀 Развёртывание — это установка программы на сервер! Как если бы ты привёз мебель в новый дом и расставил её по местам.",
                      "en": "🚀 Deployment is installing a program on a server! Like bringing furniture to a new house and arranging it."},
    "deployment": {"ru": "🚀 Развёртывание — это установка программы на сервер! Как если бы ты привёз мебель в новый дом и расставил её по местам.",
                   "en": "🚀 Deployment is installing a program on a server! Like bringing furniture to a new house and arranging it."},
    "разработка": {"ru": "🛠️ Разработка — это создание программы! Как строительство дома: сначала план, потом фундамент, потом стены. Программисты строят из кода.",
                   "en": "🛠️ Development is creating a program! Like building a house: first a plan, then a foundation, then walls. Programmers build from code."},
    "development": {"ru": "🛠️ Разработка — это создание программы! Как строительство дома: сначала план, потом фундамент, потом стены. Программисты строят из кода.",
                    "en": "🛠️ Development is creating a program! Like building a house: first a plan, then a foundation, then walls. Programmers build from code."},
    "регистр": {"ru": "📝 Регистр — это очень быстрая память внутри процессора! Как карман: маленькие, но до них можно дотянуться мгновенно.",
                "en": "📝 A register is very fast memory inside a processor! Like a pocket: small, but you can reach it instantly."},
    "register": {"ru": "📝 Регистр — это очень быстрая память внутри процессора! Как карман: маленькие, но до них можно дотянуться мгновенно.",
                 "en": "📝 A register is very fast memory inside a processor! Like a pocket: small, but you can reach it instantly."},
    "репозиторий": {"ru": "📚 Репозиторий — это хранилище кода! Как библиотека, где лежат все версии программы. Git-репозиторий — это история всех изменений.",
                    "en": "📚 A repository is a code storage! Like a library where all versions of a program are kept. A Git repository is the history of all changes."},
    "repository": {"ru": "📚 Репозиторий — это хранилище кода! Как библиотека, где лежат все версии программы. Git-репозиторий — это история всех изменений.",
                   "en": "📚 A repository is a code storage! Like a library where all versions of a program are kept. A Git repository is the history of all changes."},
    "сжатие": {"ru": "🗜️ Сжатие — это когда файл делают меньше! Как если бы ты сложил одежду вакуумным пакетом. ZIP, RAR — это форматы сжатия.",
               "en": "🗜️ Compression is when you make a file smaller! Like packing clothes in a vacuum bag. ZIP, RAR — these are compression formats."},
    "compression": {"ru": "🗜️ Сжатие — это когда файл делают меньше! Как если бы ты сложил одежду вакуумным пакетом. ZIP, RAR — это форматы сжатия.",
                    "en": "🗜️ Compression is when you make a file smaller! Like packing clothes in a vacuum bag. ZIP, RAR — these are compression formats."},
    "си": {"ru": "💻 Си (C/C++) — это мощный язык программирования! Как швейцарский нож: сложный, но может всё. На нём пишут операционные системы и игры.",
           "en": "💻 C/C++ is a powerful programming language! Like a Swiss army knife: complex, but can do everything. Operating systems and games are written in it."},
    "c": {"ru": "💻 Си (C/C++) — это мощный язык программирования! Как швейцарский нож: сложный, но может всё. На нём пишут операционные системы и игры.",
          "en": "💻 C/C++ is a powerful programming language! Like a Swiss army knife: complex, but can do everything. Operating systems and games are written in it."},
    "c++": {"ru": "💻 Си (C/C++) — это мощный язык программирования! Как швейцарский нож: сложный, но может всё. На нём пишут операционные системы и игры.",
            "en": "💻 C/C++ is a powerful programming language! Like a Swiss army knife: complex, but can do everything. Operating systems and games are written in it."},
    "синтаксис": {"ru": "📐 Синтаксис — это правила записи кода! Как грамматика в языке: если поставить запятую не там — смысл изменится. В коде тоже: одна ошибка — и программа не работает.",
                  "en": "📐 Syntax is the rules of writing code! Like grammar in language: put a comma in the wrong place — the meaning changes. In code too: one error — and the program doesn't work."},
    "syntax": {"ru": "📐 Синтаксис — это правила записи кода! Как грамматика в языке: если поставить запятую не там — смысл изменится. В коде тоже: одна ошибка — и программа не работает.",
               "en": "📐 Syntax is the rules of writing code! Like grammar in language: put a comma in the wrong place — the meaning changes. In code too: one error — and the program doesn't work."},
    "скрипт": {"ru": "📜 Скрипт — это маленькая программа-автомат! Как если бы ты написал записку: 'включи свет, потом телевизор'. Скрипт выполняет действия по порядку.",
               "en": "📜 A script is a small automation program! Like writing a note: 'turn on the light, then the TV'. A script performs actions in order."},
    "script": {"ru": "📜 Скрипт — это маленькая программа-автомат! Как если бы ты написал записку: 'включи свет, потом телевизор'. Скрипт выполняет действия по порядку.",
               "en": "📜 A script is a small automation program! Like writing a note: 'turn on the light, then the TV'. A script performs actions in order."},
    "стек": {"ru": "📚 Стек — это стопка! Как тарелки: положил сверху — взял сверху. В программировании стек хранит данные в порядке 'последний пришёл — первый вышел'.",
             "en": "📚 A stack is a pile! Like plates: put on top — take from top. In programming, a stack stores data in 'last in — first out' order."},
    "stack": {"ru": "📚 Стек — это стопка! Как тарелки: положил сверху — взял сверху. В программировании стек хранит данные в порядке 'последний пришёл — первый вышел'.",
              "en": "📚 A stack is a pile! Like plates: put on top — take from top. In programming, a stack stores data in 'last in — first out' order."},
    "субд": {"ru": "🗄️ СУБД — это программа, которая управляет базами данных! Как библиотекарь: она кладёт книги на полки и быстро находит, когда нужно. MySQL, PostgreSQL — популярные СУБД.",
             "en": "🗄️ A DBMS is a program that manages databases! Like a librarian: it puts books on shelves and finds them quickly when needed. MySQL, PostgreSQL — popular DBMS."},
    "dbms": {"ru": "🗄️ СУБД — это программа, которая управляет базами данных! Как библиотекарь: она кладёт книги на полки и быстро находит, когда нужно. MySQL, PostgreSQL — популярные СУБД.",
             "en": "🗄️ A DBMS is a program that manages databases! Like a librarian: it puts books on shelves and finds them quickly when needed. MySQL, PostgreSQL — popular DBMS."},
    "схема": {"ru": "📋 Схема — это план структуры базы данных! Как чертёж дома: где будут стены, двери, окна. Схема говорит: 'тут будет таблица пользователей, тут — заказов'.",
              "en": "📋 A schema is a database structure plan! Like a house blueprint: where walls, doors, windows go. A schema says: 'here will be the users table, here — orders'."},
    "schema": {"ru": "📋 Схема — это план структуры базы данных! Как чертёж дома: где будут стены, двери, окна. Схема говорит: 'тут будет таблица пользователей, тут — заказов'.",
               "en": "📋 A schema is a database structure plan! Like a house blueprint: where walls, doors, windows go. A schema says: 'here will be the users table, here — orders'."},
    "тестирование": {"ru": "🧪 Тестирование — это проверка программы! Как если бы ты проверил велосипед перед поездкой: тормоза, руль, колёса. Тестировщики ищут ошибки до того, как их найдут пользователи.",
                     "en": "🧪 Testing is checking a program! Like inspecting a bike before a ride: brakes, handlebars, wheels. Testers find bugs before users do."},
    "testing": {"ru": "🧪 Тестирование — это проверка программы! Как если бы ты проверил велосипед перед поездкой: тормоза, руль, колёса. Тестировщики ищут ошибки до того, как их найдут пользователи.",
                "en": "🧪 Testing is checking a program! Like inspecting a bike before a ride: brakes, handlebars, wheels. Testers find bugs before users do."},
    "токен": {"ru": "🎫 Токен — это электронный пропуск! Как билет в кино: показал — и тебя пустили. В интернете токены подтверждают, что ты — это ты.",
              "en": "🎫 A token is an electronic pass! Like a movie ticket: show it — and you're in. On the internet, tokens confirm that you are you."},
    "token": {"ru": "🎫 Токен — это электронный пропуск! Как билет в кино: показал — и тебя пустили. В интернете токены подтверждают, что ты — это ты.",
              "en": "🎫 A token is an electronic pass! Like a movie ticket: show it — and you're in. On the internet, tokens confirm that you are you."},
    "транзакция": {"ru": "💳 Транзакция — это операция, которая либо выполнена полностью, либо не выполнена вовсе! Как перевод денег: либо деньги ушли и пришли, либо ничего не произошло. Половин не бывает!",
                   "en": "💳 A transaction is an operation that's either fully completed or not done at all! Like a money transfer: either the money went and arrived, or nothing happened. No halves!"},
    "transaction": {"ru": "💳 Транзакция — это операция, которая либо выполнена полностью, либо не выполнена вовсе! Как перевод денег: либо деньги ушли и пришли, либо ничего не произошло. Половин не бывает!",
                    "en": "💳 A transaction is an operation that's either fully completed or not done at all! Like a money transfer: either the money went and arrived, or nothing happened. No halves!"},
    "утилита": {"ru": "🔧 Утилита — это маленькая полезная программа! Как отвёртка в наборе инструментов: делает одно дело, но делает его хорошо.",
                "en": "🔧 A utility is a small useful program! Like a screwdriver in a toolbox: does one thing, but does it well."},
    "utility": {"ru": "🔧 Утилита — это маленькая полезная программа! Как отвёртка в наборе инструментов: делает одно дело, но делает его хорошо.",
                "en": "🔧 A utility is a small useful program! Like a screwdriver in a toolbox: does one thing, but does it well."},
    "фреймворк": {"ru": "🏗️ Фреймворк — это каркас для программы! Как основа для конструктора: уже есть стены и крыша, а ты достраиваешь остальное.",
                  "en": "🏗️ A framework is a skeleton for a program! Like a construction base: walls and roof are already there, and you build the rest."},
    "framework": {"ru": "🏗️ Фреймворк — это каркас для программы! Как основа для конструктора: уже есть стены и крыша, а ты достраиваешь остальное.",
                  "en": "🏗️ A framework is a skeleton for a program! Like a construction base: walls and roof are already there, and you build the rest."},
    "язык программирования": {"ru": "🗣️ Язык программирования — это язык, на котором программист общается с компьютером! Python, JavaScript, C++ — у каждого свои правила и слова.",
                              "en": "🗣️ A programming language is the language a programmer uses to communicate with a computer! Python, JavaScript, C++ — each has its own rules and words."},
    "programming language": {"ru": "🗣️ Язык программирования — это язык, на котором программист общается с компьютером! Python, JavaScript, C++ — у каждого свои правила и слова.",
                             "en": "🗣️ A programming language is the language a programmer uses to communicate with a computer! Python, JavaScript, C++ — each has its own rules and words."},

    # === AI & Security / ИИ и безопасность ===
    "хакер": {"ru": "🕵️ Хакер — это человек, который умеет находить дырки в защите компьютеров. Бывают хорошие хакеры (чинят защиту) и плохие (ломают).",
              "en": "🕵️ A hacker is someone who can find holes in computer security. There are good hackers (who fix security) and bad ones (who break it)."},
    "hacker": {"ru": "🕵️ Хакер — это человек, который умеет находить дырки в защите компьютеров. Бывают хорошие хакеры (чинят защиту) и плохие (ломают).",
               "en": "🕵️ A hacker is someone who can find holes in computer security. There are good hackers (who fix security) and bad ones (who break it)."},
    "вирус": {"ru": "🦠 Вирус — это вредная программка, которая прячется в компьютере и ломает всё! Как микроб, только для электроники.",
              "en": "🦠 A virus is a harmful program that hides in a computer and breaks things! Like a germ, but for electronics."},
    "virus": {"ru": "🦠 Вирус — это вредная программка, которая прячется в компьютере и ломает всё! Как микроб, только для электроники.",
              "en": "🦠 A virus is a harmful program that hides in a computer and breaks things! Like a germ, but for electronics."},
    "антивирус": {"ru": "🛡️ Антивирус — это доктор для компьютера! Он ищет и лечит вирусы, чтобы всё работало как надо.",
                  "en": "🛡️ An antivirus is a doctor for your computer! It finds and cures viruses so everything works properly."},
    "antivirus": {"ru": "🛡️ Антивирус — это доктор для компьютера! Он ищет и лечит вирусы, чтобы всё работало как надо.",
                  "en": "🛡️ An antivirus is a doctor for your computer! It finds and cures viruses so everything works properly."},
    "фаервол": {"ru": "🧱 Фаервол — это стена между компьютером и интернетом! Он пропускает хорошее и блокирует плохое. Как охранник на входе!",
                "en": "🧱 A firewall is a wall between a computer and the internet! It lets good things through and blocks bad things. Like a security guard at the entrance!"},
    "firewall": {"ru": "🧱 Фаервол — это стена между компьютером и интернетом! Он пропускает хорошее и блокирует плохое. Как охранник на входе!",
                 "en": "🧱 A firewall is a wall between a computer and the internet! It lets good things through and blocks bad things. Like a security guard at the entrance!"},
    "брандмауэр": {"ru": "🧱 Брандмауэр — это стена между компьютером и интернетом! Он пропускает хорошее и блокирует плохое. Как охранник на входе!",
                   "en": "🧱 A firewall is a wall between a computer and the internet! It lets good things through and blocks bad things. Like a security guard at the entrance!"},
    "шифрование": {"ru": "🔐 Шифрование — это когда ты пишешь записку на секретном языке! Даже если кто-то перехватит — не сможет прочитать.",
                   "en": "🔐 Encryption is when you write a note in a secret language! Even if someone intercepts it — they can't read it."},
    "encryption": {"ru": "🔐 Шифрование — это когда ты пишешь записку на секретном языке! Даже если кто-то перехватит — не сможет прочитать.",
                   "en": "🔐 Encryption is when you write a note in a secret language! Even if someone intercepts it — they can't read it."},
    "фишинг": {"ru": "🎣 Фишинг — это когда мошенник притворяется другом, чтобы украсть твой пароль! Как удочка — наживка выглядит вкусно, но внутри крючок.",
               "en": "🎣 Phishing is when a scammer pretends to be a friend to steal your password! Like a fishing rod — the bait looks tasty, but there's a hook inside."},
    "phishing": {"ru": "🎣 Фишинг — это когда мошенник притворяется другом, чтобы украсть твой пароль! Как удочка — наживка выглядит вкусно, но внутри крючок.",
                 "en": "🎣 Phishing is when a scammer pretends to be a friend to steal your password! Like a fishing rod — the bait looks tasty, but there's a hook inside."},
    "spam": {"ru": "🗑️ Спам — это мусорные письма и сообщения! Как рекламные листовки в почтовом ящике, только в интернете.",
             "en": "🗑️ Spam is junk mail and messages! Like advertising flyers in your mailbox, but on the internet."},
    "спам": {"ru": "🗑️ Спам — это мусорные письма и сообщения! Как рекламные листовки в почтовом ящике, только в интернете.",
             "en": "🗑️ Spam is junk mail and messages! Like advertising flyers in your mailbox, but on the internet."},
    "чат-бот": {"ru": "💬 Чат-бот — это программа, которая умеет разговаривать! Как виртуальный собеседник, который всегда на связи.",
                "en": "💬 A chatbot is a program that can talk! Like a virtual conversation partner that's always available."},
    "chatbot": {"ru": "💬 Чат-бот — это программа, которая умеет разговаривать! Как виртуальный собеседник, который всегда на связи.",
                "en": "💬 A chatbot is a program that can talk! Like a virtual conversation partner that's always available."},
    "блокчейн": {"ru": "⛓️ Блокчейн — это цепочка блоков с записями! Представь тетрадь, где каждая страница приклеена к предыдущей. Невозможно вырвать страницу — все заметят. Так хранят данные в блокчейне!",
                  "en": "⛓️ Blockchain is a chain of blocks with records! Imagine a notebook where each page is glued to the previous one. You can't tear out a page — everyone would notice. That's how data is stored in blockchain!"},
    "blockchain": {"ru": "⛓️ Блокчейн — это цепочка блоков с записями! Представь тетрадь, где каждая страница приклеена к предыдущей. Невозможно вырвать страницу — все заметят. Так хранят данные в блокчейне!",
                   "en": "⛓️ Blockchain is a chain of blocks with records! Imagine a notebook where each page is glued to the previous one. You can't tear out a page — everyone would notice. That's how data is stored in blockchain!"},

    # === Social & Media / Соцсети и медиа ===
    "социальная сеть": {"ru": "👥 Социальная сеть — это как большая перемена в школе! Все общаются, делятся фотками и комментируют друг друга.",
                        "en": "👥 A social network is like a big school recess! Everyone chats, shares photos, and comments on each other."},
    "social network": {"ru": "👥 Социальная сеть — это как большая перемена в школе! Все общаются, делятся фотками и комментируют друг друга.",
                       "en": "👥 A social network is like a big school recess! Everyone chats, shares photos, and comments on each other."},
    "мессенджер": {"ru": "📲 Мессенджер — это приложение для общения! Как смс, только бесплатное и можно отправлять картинки и голосовые.",
                  "en": "📲 A messenger is an app for communication! Like SMS, but free and you can send pictures and voice messages."},
    "messenger": {"ru": "📲 Мессенджер — это приложение для общения! Как смс, только бесплатное и можно отправлять картинки и голосовые.",
                  "en": "📲 A messenger is an app for communication! Like SMS, but free and you can send pictures and voice messages."},
    "видеозвонок": {"ru": "📹 Видеозвонок — это когда ты звонишь другу и видишь его на экране! Как телевизор, только двусторонний.",
                    "en": "📹 A video call is when you call a friend and see them on screen! Like a TV, but two-way."},
    "video call": {"ru": "📹 Видеозвонок — это когда ты звонишь другу и видишь его на экране! Как телевизор, только двусторонний.",
                   "en": "📹 A video call is when you call a friend and see them on screen! Like a TV, but two-way."},
    "стрим": {"ru": "📺 Стрим — это трансляция в прямом эфире! Кто-то играет или рассказывает, а зрители смотрят в реальном времени.",
              "en": "📺 A stream is a live broadcast! Someone plays or talks, and viewers watch in real time."},
    "stream": {"ru": "📺 Стрим — это трансляция в прямом эфире! Кто-то играет или рассказывает, а зрители смотрят в реальном времени.",
               "en": "📺 A stream is a live broadcast! Someone plays or talks, and viewers watch in real time."},
    "блог": {"ru": "📝 Блог — это личный дневник в интернете! Человек пишет о своей жизни, а другие читают и комментируют.",
             "en": "📝 A blog is a personal diary on the internet! A person writes about their life, and others read and comment."},
    "blog": {"ru": "📝 Блог — это личный дневник в интернете! Человек пишет о своей жизни, а другие читают и комментируют.",
             "en": "📝 A blog is a personal diary on the internet! A person writes about their life, and others read and comment."},
    "подкаст": {"ru": "🎙️ Подкаст — это как радиопередача, только по запросу! Выбираешь тему, включаешь и слушаешь в дороге.",
                "en": "🎙️ A podcast is like a radio show, but on demand! You pick a topic, press play, and listen on the go."},
    "podcast": {"ru": "🎙️ Подкаст — это как радиопередача, только по запросу! Выбираешь тему, включаешь и слушаешь в дороге.",
                "en": "🎙️ A podcast is like a radio show, but on demand! You pick a topic, press play, and listen on the go."},
    "мем": {"ru": "😂 Мем — это смешная картинка или видео с подписью! Как шутка, только в интернете и с картинкой.",
            "en": "😂 A meme is a funny picture or video with a caption! Like a joke, but on the internet and with an image."},
    "meme": {"ru": "😂 Мем — это смешная картинка или видео с подписью! Как шутка, только в интернете и с картинкой.",
             "en": "😂 A meme is a funny picture or video with a caption! Like a joke, but on the internet and with an image."},
    "лайк": {"ru": "👍 Лайк — это когда тебе что-то понравилось! Как если бы ты показал большой палец вверх.",
             "en": "👍 A like is when you enjoy something! Like giving a thumbs up."},
    "like": {"ru": "👍 Лайк — это когда тебе что-то понравилось! Как если бы ты показал большой палец вверх.",
             "en": "👍 A like is when you enjoy something! Like giving a thumbs up."},
    "репост": {"ru": "🔄 Репост — это когда ты делишься чужой записью у себя! Как если бы ты дал другу почитать интересную статью.",
               "en": "🔄 A repost is when you share someone else's post on your page! Like lending a friend an interesting article to read."},
    "repost": {"ru": "🔄 Репост — это когда ты делишься чужой записью у себя! Как если бы ты дал другу почитать интересную статью.",
               "en": "🔄 A repost is when you share someone else's post on your page! Like lending a friend an interesting article to read."},

    # === Misc / Разное ===
    "пиксель": {"ru": "🟦 Пиксель — это маленький цветной квадратик, из которых состоит картинка на экране! Как мозаика, только электронная.",
                "en": "🟦 A pixel is a tiny colored square that makes up an image on screen! Like a mosaic, but electronic."},
    "pixel": {"ru": "🟦 Пиксель — это маленький цветной квадратик, из которых состоит картинка на экране! Как мозаика, только электронная.",
              "en": "🟦 A pixel is a tiny colored square that makes up an image on screen! Like a mosaic, but electronic."},
    "разрешение": {"ru": "📐 Разрешение — это сколько пикселей на экране! Чем больше — тем четче картинка. Как количество точек на рисунке!",
                   "en": "📐 Resolution is how many pixels are on screen! The more — the clearer the image. Like the number of dots in a drawing!"},
    "resolution": {"ru": "📐 Разрешение — это сколько пикселей на экране! Чем больше — тем четче картинка. Как количество точек на рисунке!",
                   "en": "📐 Resolution is how many pixels are on screen! The more — the clearer the image. Like the number of dots in a drawing!"},
    "формат": {"ru": "📋 Формат — это тип файла! Картинка, текст, видео — у каждого свой формат. Как разные виды упаковок для разных вещей.",
               "en": "📋 A format is a file type! Image, text, video — each has its own format. Like different kinds of packaging for different things."},
    "format": {"ru": "📋 Формат — это тип файла! Картинка, текст, видео — у каждого свой формат. Как разные виды упаковок для разных вещей.",
               "en": "📋 A format is a file type! Image, text, video — each has its own format. Like different kinds of packaging for different things."},
    "копировать вставить": {"ru": "📋 Копировать-вставить — это когда ты берёшь что-то и делаешь копию! Как ксерокс, только в компьютере.",
                            "en": "📋 Copy-paste is when you take something and make a copy! Like a photocopier, but in a computer."},
    "copy paste": {"ru": "📋 Копировать-вставить — это когда ты берёшь что-то и делаешь копию! Как ксерокс, только в компьютере.",
                   "en": "📋 Copy-paste is when you take something and make a copy! Like a photocopier, but in a computer."},
    "login": {"ru": "🔑 Логин — это твоё имя для входа в систему! Как имя на бейджике, только для компьютера.",
              "en": "🔑 A login is your name to enter a system! Like a name badge, but for a computer."},
    "логин": {"ru": "🔑 Логин — это твоё имя для входа в систему! Как имя на бейджике, только для компьютера.",
              "en": "🔑 A login is your name to enter a system! Like a name badge, but for a computer."},
    "аккаунт": {"ru": "👤 Аккаунт — это твой личный кабинет в интернете! Там хранятся все твои настройки, друзья и данные.",
                "en": "👤 An account is your personal space on the internet! All your settings, friends, and data are stored there."},
    "account": {"ru": "👤 Аккаунт — это твой личный кабинет в интернете! Там хранятся все твои настройки, друзья и данные.",
                "en": "👤 An account is your personal space on the internet! All your settings, friends, and data are stored there."},
    "регистрация": {"ru": "📝 Регистрация — это когда ты создаёшь свой аккаунт! Как записаться в библиотеку, только онлайн.",
                    "en": "📝 Registration is when you create your account! Like signing up for a library, but online."},
    "registration": {"ru": "📝 Регистрация — это когда ты создаёшь свой аккаунт! Как записаться в библиотеку, только онлайн.",
                     "en": "📝 Registration is when you create your account! Like signing up for a library, but online."},
    "настройки": {"ru": "⚙️ Настройки — это пульт управления программой! Там можно выбрать язык, цвет, звук и другие вещи под себя.",
                  "en": "⚙️ Settings are the control panel for a program! You can choose language, color, sound, and other things to your liking."},
    "settings": {"ru": "⚙️ Настройки — это пульт управления программой! Там можно выбрать язык, цвет, звук и другие вещи под себя.",
                 "en": "⚙️ Settings are the control panel for a program! You can choose language, color, sound, and other things to your liking."},
    "notification": {"ru": "🔔 Уведомление — это сигнал, что что-то случилось! Как колокольчик: динь-динь — у тебя новое сообщение!",
                     "en": "🔔 A notification is a signal that something happened! Like a little bell: ding-ding — you have a new message!"},
    "уведомление": {"ru": "🔔 Уведомление — это сигнал, что что-то случилось! Как колокольчик: динь-динь — у тебя новое сообщение!",
                    "en": "🔔 A notification is a signal that something happened! Like a little bell: ding-ding — you have a new message!"},
    "тема": {"ru": "🎨 Тема оформления — это как одежда для программы! Можно выбрать тёмную, светлую или цветную.",
             "en": "🎨 A theme is like clothing for a program! You can choose dark, light, or colorful."},
    "theme": {"ru": "🎨 Тема оформления — это как одежда для программы! Можно выбрать тёмную, светлую или цветную.",
              "en": "🎨 A theme is like clothing for a program! You can choose dark, light, or colorful."},
    "иконка": {"ru": "🖼️ Иконка — это маленькая картинка, которая обозначает программу или файл! Как вывеска магазина, только на экране.",
               "en": "🖼️ An icon is a small picture that represents a program or file! Like a shop sign, but on screen."},
    "icon": {"ru": "🖼️ Иконка — это маленькая картинка, которая обозначает программу или файл! Как вывеска магазина, только на экране.",
             "en": "🖼️ An icon is a small picture that represents a program or file! Like a shop sign, but on screen."},
    "вектор": {"ru": "➡️ Вектор — это направление и сила! Как стрелка на карте: она показывает, куда идти и как далеко. В графике вектор — это линия, которая не теряет качество при увеличении.",
               "en": "➡️ A vector is direction and magnitude! Like an arrow on a map: it shows where to go and how far. In graphics, a vector is a line that doesn't lose quality when scaled."},
    "vector": {"ru": "➡️ Вектор — это направление и сила! Как стрелка на карте: она показывает, куда идти и как далеко. В графике вектор — это линия, которая не теряет качество при увеличении.",
               "en": "➡️ A vector is direction and magnitude! Like an arrow on a map: it shows where to go and how far. In graphics, a vector is a line that doesn't lose quality when scaled."},
    "экран": {"ru": "🖥️ Экран — это окно в мир компьютера! Всё, что ты видишь — картинки, текст, видео — появляется на экране.",
              "en": "🖥️ A screen is a window to the computer world! Everything you see — images, text, video — appears on the screen."},
    "screen": {"ru": "🖥️ Экран — это окно в мир компьютера! Всё, что ты видишь — картинки, текст, видео — появляется на экране.",
               "en": "🖥️ A screen is a window to the computer world! Everything you see — images, text, video — appears on the screen."},
    "бэкап": {"ru": "💾 Бэкап — это копия важных вещей! Как если бы ты сфотографировал все свои игрушки на случай, если что-то потеряешь.",
              "en": "💾 A backup is a copy of important stuff! Like photographing all your toys in case you lose something."},
    "backup": {"ru": "💾 Бэкап — это копия важных вещей! Как если бы ты сфотографировал все свои игрушки на случай, если что-то потеряешь.",
               "en": "💾 A backup is a copy of important stuff! Like photographing all your toys in case you lose something."},
    "скачать": {"ru": "⬇️ Скачать — это сохранить что-то из интернета на свой компьютер! Как забрать книгу из библиотеки домой.",
                "en": "⬇️ Download is saving something from the internet to your computer! Like taking a book home from the library."},
    "download": {"ru": "⬇️ Скачать — это сохранить что-то из интернета на свой компьютер! Как забрать книгу из библиотеки домой.",
                 "en": "⬇️ Download is saving something from the internet to your computer! Like taking a book home from the library."},
    "загрузить": {"ru": "⬆️ Загрузить — это отправить что-то из своего компьютера в интернет! Как положить письмо в почтовый ящик.",
                  "en": "⬆️ Upload is sending something from your computer to the internet! Like putting a letter in a mailbox."},
    "upload": {"ru": "⬆️ Загрузить — это отправить что-то из своего компьютера в интернет! Как положить письмо в почтовый ящик.",
               "en": "⬆️ Upload is sending something from your computer to the internet! Like putting a letter in a mailbox."},
}

INTROS_RU = [
    "Отличный вопрос! 🎉",
    "Давай объясню! 😊",
    "Это интересно! 🌟",
    "Проще простого! ✨",
    "Смотри! 👀",
]

INTROS_EN = [
    "Great question! 🎉",
    "Let me explain! 😊",
    "That's interesting! 🌟",
    "Easy peasy! ✨",
    "Check this out! 👀",
]

OUTROS_RU = [
    "\n\nПонятно? Если хочешь узнать ещё — спрашивай! 😄",
    "\n\nТеперь ты знаешь чуть больше! 🎈",
    "\n\nЛегко, правда? Давай ещё! 🚀",
    "\n\nНадеюсь, стало понятнее! 💫",
]

OUTROS_EN = [
    "\n\nGot it? If you want to learn more — just ask! 😄",
    "\n\nNow you know a little more! 🎈",
    "\n\nEasy, right? Let's go again! 🚀",
    "\n\nHope that makes sense! 💫",
]


def generate_explanation(term: str, language: str = 'ru') -> str:
    """Generate a simple explanation for a term in the detected language."""
    term_lower = term.lower()

    # Check if we have a predefined explanation
    if term_lower in EXPLANATIONS:
        return EXPLANATIONS[term_lower].get(language, EXPLANATIONS[term_lower]['ru'])

    # Generic explanation for unknown terms
    if language == 'en':
        intro = random.choice(INTROS_EN)
        outro = random.choice(OUTROS_EN)
        return (
            f"{intro}\n\n"
            f"🤖 **{term}** is like a little helper in the world of big ideas! "
            f"Imagine you have a magic box that helps you do cool things. "
            f"Every day it learns something new and gets smarter!"
            f"{outro}"
        )
    else:
        intro = random.choice(INTROS_RU)
        outro = random.choice(OUTROS_RU)
        return (
            f"{intro}\n\n"
            f"🤖 **{term}** — это как маленький помощник в мире больших идей! "
            f"Представь, что у тебя есть волшебная коробочка, которая помогает делать крутые вещи. "
            f"Каждый день она учится новому и становится умнее!"
            f"{outro}"
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="ELI5 AI Explainer")


@app.on_event("startup")
def on_startup():
    init_db()


# Serve static files and the SPA entry point
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ExplainRequest(BaseModel):
    term: str


class ExplainResponse(BaseModel):
    term: str
    explanation: str
    language: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(req: ExplainRequest):
    term = req.term.strip()
    language = detect_language(term)

    # Generate explanation locally (no LLM needed)
    explanation = generate_explanation(term, language)

    # Save to SQLite
    with get_db() as conn:
        conn.execute(
            "INSERT INTO explanations (term, explanation, language) VALUES (?, ?, ?)",
            (term, explanation, language),
        )

    return {"term": term, "explanation": explanation, "language": language}


@app.get("/api/history")
async def history():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, term, explanation, language FROM explanations ORDER BY id DESC"
        ).fetchall()

    return [{"id": r["id"], "term": r["term"], "explanation": r["explanation"], "language": r["language"]} for r in rows]


# ---------------------------------------------------------------------------
# V2 Routes — Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# V2 Routes — Search, Delete, Stats, Popular terms
# ---------------------------------------------------------------------------


@app.get("/api/search")
async def search_history(q: str = Query(..., min_length=1)):
    """Search explanations by term or content (case-insensitive)."""
    pattern = f"%{q}%"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, term, explanation, language FROM explanations "
            "WHERE term LIKE ? OR explanation LIKE ? "
            "ORDER BY id DESC",
            (pattern, pattern),
        ).fetchall()

    return [{"id": r["id"], "term": r["term"], "explanation": r["explanation"], "language": r["language"]} for r in rows]


@app.delete("/api/history/{entry_id}")
async def delete_entry(entry_id: int):
    """Delete a single history entry by ID."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM explanations WHERE id = ?", (entry_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Entry not found")

    return {"deleted": entry_id}


@app.delete("/api/history")
async def clear_history():
    """Delete all history entries."""
    with get_db() as conn:
        conn.execute("DELETE FROM explanations")

    return {"cleared": True}


@app.get("/api/stats")
async def stats():
    """Return usage statistics."""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM explanations").fetchone()[0]
        unique_terms = conn.execute(
            "SELECT COUNT(DISTINCT LOWER(term)) FROM explanations"
        ).fetchone()[0]

    return {"total_explanations": total, "unique_terms": unique_terms}


@app.get("/api/popular")
async def popular(limit: int = Query(5, ge=1, le=20)):
    """Return the most frequently requested terms."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT LOWER(term) as term, COUNT(*) as cnt "
            "FROM explanations "
            "GROUP BY LOWER(term) "
            "ORDER BY cnt DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [{"term": r["term"], "count": r["cnt"]} for r in rows]
