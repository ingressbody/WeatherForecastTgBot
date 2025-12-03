import os
import sys
import requests
import json
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
import logging
import sqlite3

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
#WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')  # Альтернативный API

# Координаты озера Ладога (примерные центральные координаты)
LADOGA_COORDS = {
    'lat': 61.111969,
    'lon': 30.339632
}

class WeatherBot:
    def __init__(self):
        self.keyboard = [ ["🌤️ Погода на 3 дня", "🗺️ Текущая локация", "❓ Помощь"] ]
        self.keyboard_markup = ReplyKeyboardMarkup(self.keyboard, resize_keyboard=True)
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        conn = sqlite3.connect("usersdb.sqlite", isolation_level=None)
        self.cursor = conn.cursor()
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tgid INTEGER PRIMARY KEY AUTOINCREMENT,
                    lat REAL,
                    lon REAL
                )
            """)
            print("Table 'users' created successfully or already exists.")
        except sqlite3.Error as e:
            print(f"Error creating table: {e}")
            sys.exit("Error creating table: {e}")
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("weather", self.weather_command))
        self.application.add_handler(CommandHandler("location", self.location_command))
        #self.application.add_handler(CommandHandler("set_location", self.set_location_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.handle_location))  # Добавьте эту строку
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        await update.message.reply_text(
            "👋 Добро пожаловать в бот погоды на Ладожском озере!\n\n"
            "Выберите опцию ниже или используйте команды:\n"
            "/weather - текущая погода\n"
            "/help - справка",
            reply_markup = self.keyboard_markup
        )

    async def location_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /location"""
        user_id = update.message.from_user.id
        lat,lon = self.get_user_location_db(user_id)
        if lat and lon:
            await update.message.reply_text(f"Текущие координаты: {lat}, {lon}", reply_markup = self.keyboard_markup)
        else:
            await update.message.reply_text("Координаты не заданы", reply_markup = self.keyboard_markup)
    
    async def weather_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /weather"""
        await self.send_weather_forecast(update, context, days=3)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🌊 Бот погоды для Ладожского озера

Доступные команды:
/start - начать работу
/weather - погода на 3 дня
/help - эта справка
/location - заданные координаты

Или используйте кнопки меню для навигации.

Бот показывает:
• Температуру (°C)
• Осадки и облачность
• Направление и скорость ветра
• Влажность и давление
"""
        await update.message.reply_text(help_text, reply_markup = self.keyboard_markup)


    def get_user_location_db(self, usertg_id):
        """Взять координаты пользователя из БД"""
        self.cursor.execute(f"SELECT * FROM users WHERE tgid={usertg_id}")
        rows = self.cursor.fetchall()
        if rows:
            lat = rows[0][1]
            lon = rows[0][2]
        else:
            lat = LADOGA_COORDS["lat"]
            lon = LADOGA_COORDS["lon"]
        return lat,lon
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        text = update.message.text.lower()
        if text in self.keyboard[0][0].lower():
            await self.send_weather_forecast(update, context, days=3)
        elif text in self.keyboard[0][1].lower():
            await self.location_command(update, context)
        elif text in self.keyboard[0][2].lower():
            await self.help_command(update, context)
        else:
            await update.message.reply_text("Используйте кнопки меню или команды для навигации", reply_markup = self.keyboard_markup)


    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка отправленной геолокации"""
        user_id = update.message.from_user.id
        location = update.message.location
        
        if location:
            lat = location.latitude
            lon = location.longitude            
            
            query = f"SELECT 1 FROM users WHERE tgid = {user_id}"
            self.cursor.execute(query)
            row_exists = self.cursor.fetchone()
            if row_exists:
                self.cursor.execute(f"UPDATE users SET lat={lat}, lon={lon} WHERE tgid = {user_id}")
            else:
                q = f"INSERT INTO users (tgid, lat, lon) VALUES ({user_id}, {lat}, {lon})"
                self.cursor.execute(q)
            
            await update.message.reply_text(
                f"📍 Геолокация принята!\n"
                f"📌 Координаты: {lat:.4f}, {lon:.4f}\n\n"
                f"Хотите посмотреть погоду для этой точки?",
                reply_markup = self.keyboard_markup
            )

    def get_wind_direction(self, degrees):
        """Преобразование градусов в направление ветра"""
        directions = ['С', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
        index = round(degrees / 45) % 8
        return directions[index]
    
    def get_weather_icon(self, weather_id):
        """Получение emoji для погодных условий"""
        if weather_id in [800]:
            return "☀️"
        elif weather_id in [801, 802]:
            return "⛅"
        elif weather_id in [803, 804]:
            return "☁️"
        elif weather_id in [300, 301, 302, 310, 311, 312, 313, 314, 321, 500, 501, 502, 503, 504]:
            return "🌧️"
        elif weather_id in [511, 611, 612, 613, 615, 616, 620, 621, 622]:
            return "🌨️"
        elif weather_id in [200, 201, 202, 210, 211, 212, 221, 230, 231, 232]:
            return "⛈️"
        elif weather_id in [600, 601, 602]:
            return "❄️"
        elif weather_id in [701, 711, 721, 731, 741, 751, 761, 762, 771, 781]:
            return "🌫️"
        else:
            return "🌤️"
    
    async def get_weather_data(self, lat, lon, days=3):
        """Получение данных о погоде с OpenWeatherMap API"""
        try:
            if days <= 5:
                # Прогноз на 5 дней (3 часа интервал)
                url = "https://api.openweathermap.org/data/2.5/forecast"
                params = {
                    'lat': lat,
                    'lon': lon,
                    'appid': OPENWEATHER_API_KEY,
                    'units': 'metric',
                    'lang': 'ru'
                }
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                return self.parse_5day_forecast(data, days)
            else:
                # Прогноз на 16 дней (требуется платная подписка)
                # Используем бесплатный вариант с ограничением
                return None            
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка запроса к API: {e}")
            return None
        except Exception as e:
            logging.error(f"Ошибка обработки данных: {e}")
            return None
    
    def parse_5day_forecast(self, data, days):
        """Парсинг 5-дневного прогноза"""
        forecast_data = {}
        
        for item in data['list']:
            date = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
            time = datetime.fromtimestamp(item['dt']).strftime('%H:%M')
            
            if date not in forecast_data:
                forecast_data[date] = {
                    'date': datetime.fromtimestamp(item['dt']).strftime('%d.%m.%Y'),
                    'day_name': self.get_russian_day(datetime.fromtimestamp(item['dt'])),
                    'temps': [],
                    'humidity': [],
                    'pressure': [],
                    'weather': [],
                    'wind_speed': [],
                    'wind_deg': []
                }
            
            forecast_data[date]['temps'].append(item['main']['temp'])
            forecast_data[date]['humidity'].append(item['main']['humidity'])
            forecast_data[date]['pressure'].append(item['main']['pressure'])
            forecast_data[date]['weather'].append({
                'main': item['weather'][0]['main'],
                'description': item['weather'][0]['description'],
                'id': item['weather'][0]['id']
            })
            forecast_data[date]['wind_speed'].append(item['wind']['speed'])
            forecast_data[date]['wind_deg'].append(item['wind'].get('deg', 0))
        
        # Ограничиваем количество дней
        sorted_dates = sorted(forecast_data.keys())[:days]
        return [forecast_data[date] for date in sorted_dates]
    
    def get_russian_day(self, date):
        """Получение названия дня недели на русском"""
        days = {
            'Monday': 'Понедельник',
            'Tuesday': 'Вторник',
            'Wednesday': 'Среда',
            'Thursday': 'Четверг',
            'Friday': 'Пятница',
            'Saturday': 'Суббота',
            'Sunday': 'Воскресенье'
        }
        english_day = date.strftime('%A')
        return days.get(english_day, english_day)
    
    async def send_weather_forecast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, days=3):
        """Отправка прогноза погоды"""
        await update.message.reply_text("⏳ Получаю актуальные данные о погоде...", reply_markup = self.keyboard_markup)
        
        user_id = update.message.from_user.id
        lat,lon = self.get_user_location_db(user_id)
        if not (lat and lon):            
            lat = LADOGA_COORDS['lat']
            lon = LADOGA_COORDS['lon']

        weather_data = await self.get_weather_data(lat, lon, days)
        
        if not weather_data:
            await update.message.reply_text(
                "❌ Не удалось получить данные о погоде. "
                "Попробуйте позже или проверьте настройки API.",
                reply_markup = self.keyboard_markup
            )
            return
        
        response_text = f"🌊 **Погода на Ладожском озере**\n\n"
        
        for day_data in weather_data:
            # Средние/максимальные значения за день
            avg_temp = round(sum(day_data['temps']) / len(day_data['temps']), 1)
            max_temp = round(max(day_data['temps']), 1)
            min_temp = round(min(day_data['temps']), 1)
            
            avg_wind_speed = round(sum(day_data['wind_speed']) / len(day_data['wind_speed']), 1)
            avg_wind_deg = sum(day_data['wind_deg']) / len(day_data['wind_deg'])
            wind_direction = self.get_wind_direction(avg_wind_deg)
            
            # Самый частый тип погоды
            main_weather = max(set([w['main'] for w in day_data['weather']]), 
                             key=[w['main'] for w in day_data['weather']].count)
            weather_icon = self.get_weather_icon(day_data['weather'][0]['id'])
            
            response_text += (
                f"**{day_data['day_name']} ({day_data['date']})** {weather_icon}\n"
                f"• Температура: {min_temp}°C ... {max_temp}°C\n"
                f"• Осадки: {day_data['weather'][0]['description']}\n"
                f"• Ветер: {wind_direction} {avg_wind_speed} м/с\n"
                f"• Влажность: {day_data['humidity'][0]}%\n"
                f"• Давление: {day_data['pressure'][0]} гПа\n\n"
            )
        
        response_text += f"📍 *Координаты:* {lat}, {lon}\n"
        response_text += "🕒 *Обновлено:* " + datetime.now().strftime("%d.%m.%Y %H:%M")
        
        await update.message.reply_text(response_text, parse_mode='Markdown', reply_markup = self.keyboard_markup)
    
    def run(self):
        """Запуск бота"""
        print("Бот погоды запущен...")
        self.application.run_polling()

# Создание и запуск бота
if __name__ == "__main__":
    bot = WeatherBot()
    bot.run()
