import requests
import json
import time
import os
import datetime
from dotenv import load_dotenv

# Load environment variables (for Telegram Bot Token & Chat ID)
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Configuration
CHECK_DATES = [
    "21-03-2026 21:00:00",
    "22-03-2026 21:00:00"
]
CHECK_INTERVAL_SECONDS = 300

# To prevent spamming, store which (train_number, date) we have already notified about
notified_trains = set()

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"Skipping Telegram notification (Token or Chat ID missing). Message:\n{message}")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Telegram notification sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

def check_train_availability(departure_date):
    url = "https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms/train/train-availability?environment=dev&userId=1"

    # Note: Content-Length and Accept-Encoding (gzip, deflate) are usually handled automatically by the requests library, so they are omitted here.
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr",
        "User-Authorization": os.getenv("USER_AUTHORIZATION", ""),
        "Authorization": os.getenv("AUTHORIZATION", ""),
        "unit-id": "3895",
        "Content-Type": "application/json",
        "Origin": "https://ebilet.tcddtasimacilik.gov.tr",
        "Connection": "keep-alive"
    }

    payload = {
        "searchRoutes": [
            {
                "departureStationId": 1336,
                "departureStationName": "SELÇUKLU YHT (KONYA)",
                "arrivalStationId": 48,
                "arrivalStationName": "İSTANBUL(PENDİK)",
                "departureDate": departure_date
            }
        ],
        "passengerTypeCounts": [
            {
                "id": 0,
                "count": 1
            }
        ],
        "searchReservation": False,
        "searchType": "DOMESTIC",
        "blTrainTypes": [
            "TURISTIK_TREN"
        ]
    }

    try:
        # Use json=payload to automatically encode the dict to JSON format
        response = requests.post(url, headers=headers, json=payload)
        
        # Raise an error if the request failed (e.g., 401 Unauthorized, 403 Forbidden)
        response.raise_for_status()

        # Parse the JSON response
        data = response.json()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Success! Retrieved API data for {departure_date}.")
        
        # Parse logic
        train_legs = data.get("trainLegs", [])
        if not train_legs:
            print("No train legs found.")
            return

        for leg in train_legs:
            for availability in leg.get("trainAvailabilities", []):
                for train in availability.get("trains", []):
                    train_name = train.get("name", "Unknown Train")
                    train_number = train.get("number", "Unknown")
                    
                    # Extract the true departure time instead of just the query date
                    exact_departure_time = "Unknown Time"
                    segments = train.get("segments", [])
                    if segments:
                        ts = segments[0].get("departureTime")
                        if ts:
                            exact_departure_time = datetime.datetime.fromtimestamp(ts/1000).strftime('%H:%M')

                    found_economy = False
                    economy_available = 0
                    
                    for car in train.get("cars", []):
                        for avail in car.get("availabilities", []):
                            cabin_class = avail.get("cabinClass")
                            if cabin_class:
                                class_id = cabin_class.get("id")
                                # 2 = EKONOMİ, 12 = TEKERLEKLİ SANDALYE (Disabled)
                                # We only want to count Economy seats (id == 2)
                                if class_id == 2:
                                    available_seats = avail.get("availability", 0)
                                    if available_seats > 0:
                                        found_economy = True
                                        economy_available += available_seats
                    
                    # We just use the date part of our query string to map notifications
                    base_date = departure_date.split(" ")[0]

                    if found_economy:
                        msg = f"Train {train_number} ({exact_departure_time}) has {economy_available} Economy seats AVAILABLE on {base_date}!"
                        print(f"AVAILABLE: {msg}")
                        
                        # Check if we should send a notification
                        notify_key = f"{train_number}_{base_date}"
                        if notify_key not in notified_trains:
                            send_telegram_message(f"🚂 TCDD Bot Alert!\n{msg}")
                            notified_trains.add(notify_key)
                    else:
                        print(f"Train {train_number} ({exact_departure_time}) has no Economy seats available on {base_date}.")

        return data

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - Status Code: {response.status_code}")
        # print(response.text)
    except Exception as err:
        print(f"Other error occurred: {err}")

# Bot loop
if __name__ == "__main__":
    print("Starting TCDD Ticket Bot...")
    
    # Simple loop to check repeatedly
    while True:
        for date in CHECK_DATES:
            check_train_availability(date)
        
        # Wait before the next request to avoid getting IP banned
        print(f"Waiting {CHECK_INTERVAL_SECONDS} seconds before checking again...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)


