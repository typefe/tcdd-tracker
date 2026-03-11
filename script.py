import requests
import json
import time
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load environment variables (for Telegram Bot Token & Chat ID)
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Turkey timezone (UTC+3)
TURKEY_TZ = timezone(timedelta(hours=3))

# Configure logging with ISO8601 timestamps
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Configuration from environment
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL", "300"))

# Retry configuration
RETRY_DELAYS = [5, 10, 30, 60]  # seconds
REQUEST_TIMEOUT = 30
RATE_LIMIT_BACKOFF = 120  # seconds

# Failure tracking
consecutive_failures = 0
SUSTAINED_FAILURE_THRESHOLD = 4

# To prevent spamming, store which (train_number, date) we have already notified about
notified_trains = set()

# Route mapping for the 3 main stations
ROUTE_MAP = {
    "ISTANBUL-KONYA": {
        "from_id": 48,
        "from_name": "İSTANBUL(PENDİK)",
        "to_id": 1336,
        "to_name": "SELÇUKLU YHT (KONYA)",
    },
    "ISTANBUL-ANKARA": {
        "from_id": 48,
        "from_name": "İSTANBUL(PENDİK)",
        "to_id": 98,
        "to_name": "ANKARA GAR",
    },
    "ANKARA-ISTANBUL": {
        "from_id": 98,
        "from_name": "ANKARA GAR",
        "to_id": 48,
        "to_name": "İSTANBUL(PENDİK)",
    },
    "ANKARA-KONYA": {
        "from_id": 98,
        "from_name": "ANKARA GAR",
        "to_id": 1336,
        "to_name": "SELÇUKLU YHT (KONYA)",
    },
    "KONYA-ISTANBUL": {
        "from_id": 1336,
        "from_name": "SELÇUKLU YHT (KONYA)",
        "to_id": 48,
        "to_name": "İSTANBUL(PENDİK)",
    },
    "KONYA-ANKARA": {
        "from_id": 1336,
        "from_name": "SELÇUKLU YHT (KONYA)",
        "to_id": 98,
        "to_name": "ANKARA GAR",
    },
}


def parse_check_dates():
    """Parse CHECK_DATES env var, validate format and not in past."""
    dates_str = os.getenv("CHECK_DATES", "")
    if not dates_str:
        logger.error("CHECK_DATES environment variable is empty")
        send_telegram_message(
            "🚨 TCDD Bot: CHECK_DATES environment variable is empty. Bot cannot start."
        )
        sys.exit(1)

    valid_dates = []
    invalid_dates = []
    now_turkey = datetime.now(TURKEY_TZ)
    today_start = now_turkey.replace(hour=0, minute=0, second=0, microsecond=0)

    for date_str in dates_str.split(","):
        date_str = date_str.strip()
        if not date_str:
            continue
        try:
            # Parse DD-MM-YYYY format
            parsed = datetime.strptime(date_str, "%d-%m-%Y")
            # Add timezone info for comparison
            parsed_with_tz = parsed.replace(tzinfo=TURKEY_TZ)
            # Check not in past
            if parsed_with_tz < today_start:
                invalid_dates.append(f"{date_str} (past date)")
            else:
                # Fixed hour at 21:00
                valid_dates.append(f"{date_str} 21:00:00")
        except ValueError:
            invalid_dates.append(f"{date_str} (invalid format)")

    if invalid_dates:
        send_telegram_message(
            f"⚠️ TCDD Bot: Invalid dates in config: {', '.join(invalid_dates)}"
        )
        logger.warning(f"Invalid dates skipped: {invalid_dates}")

    if not valid_dates:
        logger.error("No valid dates to monitor")
        send_telegram_message(
            "🚨 TCDD Bot: No valid dates to monitor. Bot cannot start."
        )
        sys.exit(1)

    logger.info(f"Monitoring {len(valid_dates)} date(s): {valid_dates}")
    return valid_dates


def parse_routes():
    """Parse ROUTES env var, validate each route exists in ROUTE_MAP."""
    routes_str = os.getenv("ROUTES", "")
    if not routes_str:
        logger.error("ROUTES environment variable is empty or not set")
        send_telegram_message(
            "🚨 TCDD Bot: ROUTES environment variable is empty or not set. Bot cannot start."
        )
        sys.exit(1)

    valid_routes = []
    invalid_routes = []

    for route in routes_str.split(","):
        route = route.strip().upper()
        if not route:
            continue
        if route in ROUTE_MAP:
            valid_routes.append(route)
        else:
            invalid_routes.append(route)

    if invalid_routes:
        error_msg = f"Invalid route(s): {', '.join(invalid_routes)}"
        logger.error(error_msg)
        send_telegram_message(f"🚨 TCDD Bot: {error_msg}")
        sys.exit(1)

    if not valid_routes:
        logger.error("No valid routes to monitor")
        send_telegram_message(
            "🚨 TCDD Bot: No valid routes to monitor. Bot cannot start."
        )
        sys.exit(1)

    logger.info(f"Monitoring {len(valid_routes)} route(s): {valid_routes}")
    return valid_routes


def send_telegram_message(message):
    """Send a message via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(
            f"Skipping Telegram notification (Token or Chat ID missing). Message:\n{message}"
        )
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


def check_with_retry(departure_date, route):
    """Check train availability with retry logic and exponential backoff."""
    global consecutive_failures

    route_info = ROUTE_MAP[route]

    url = "https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms/train/train-availability?environment=dev&userId=1"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr",
        "User-Authorization": os.getenv("USER_AUTHORIZATION", ""),
        "Authorization": os.getenv("AUTHORIZATION", ""),
        "unit-id": "3895",
        "Content-Type": "application/json",
        "Origin": "https://ebilet.tcddtasimacilik.gov.tr",
        "Connection": "keep-alive",
    }

    payload = {
        "searchRoutes": [
            {
                "departureStationId": route_info["from_id"],
                "departureStationName": route_info["from_name"],
                "arrivalStationId": route_info["to_id"],
                "arrivalStationName": route_info["to_name"],
                "departureDate": departure_date,
            }
        ],
        "passengerTypeCounts": [{"id": 0, "count": 1}],
        "searchReservation": False,
        "searchType": "DOMESTIC",
        "blTrainTypes": ["YHT"],
    }

    for attempt, delay in enumerate(RETRY_DELAYS):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )

            # Handle 429 rate limit with longer backoff
            if response.status_code == 429:
                logger.warning(
                    f"Rate limited (429), waiting {RATE_LIMIT_BACKOFF}s before retry"
                )
                time.sleep(RATE_LIMIT_BACKOFF)
                continue

            response.raise_for_status()
            data = response.json()

            # Success - reset failure counter
            was_in_sustained_failure = (
                consecutive_failures >= SUSTAINED_FAILURE_THRESHOLD
            )
            consecutive_failures = 0

            if was_in_sustained_failure:
                logger.info("API connection restored after sustained failure")
                send_telegram_message("✅ TCDD Bot: API connection restored")

            logger.info(f"Success! Retrieved API data for {route} on {departure_date}")
            return data

        except requests.Timeout:
            logger.warning(
                f"Request timeout (attempt {attempt + 1}/{len(RETRY_DELAYS)}) for {route} on {departure_date}"
            )
        except requests.ConnectionError as e:
            logger.warning(
                f"Connection error (attempt {attempt + 1}/{len(RETRY_DELAYS)}): {e}"
            )
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else "unknown"
            logger.error(f"HTTP error: {e} - Status Code: {status_code}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        # Wait before next retry (except on last attempt)
        if attempt < len(RETRY_DELAYS) - 1:
            logger.info(f"Retrying in {delay}s...")
            time.sleep(delay)

    # All retries exhausted for this check
    consecutive_failures += 1
    logger.error(
        f"API check failed for {route} on {departure_date}. Consecutive failures: {consecutive_failures}"
    )

    # Send sustained failure alert only once when threshold is reached
    if consecutive_failures == SUSTAINED_FAILURE_THRESHOLD:
        send_telegram_message(
            "🚨 TCDD Bot: API connection failed after multiple retries. Sustained failure detected."
        )

    return None


def process_train_data(data, departure_date):
    """Process API response and check for available seats."""
    train_legs = data.get("trainLegs", [])
    if not train_legs:
        logger.info("No train legs found")
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
                        exact_departure_time = datetime.fromtimestamp(
                            ts / 1000
                        ).strftime("%H:%M")

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
                    logger.info(f"AVAILABLE: {msg}")

                    # Check if we should send a notification
                    notify_key = f"{train_number}_{base_date}"
                    if notify_key not in notified_trains:
                        send_telegram_message(f"🚂 TCDD Bot Alert!\n{msg}")
                        notified_trains.add(notify_key)
                else:
                    logger.info(
                        f"Train {train_number} ({exact_departure_time}) has no Economy seats available on {base_date}"
                    )


def check_train_availability(departure_date, route):
    """Check train availability for a specific date and route."""
    logger.info(f"Checking route: {route}")
    data = check_with_retry(departure_date, route)
    if data:
        process_train_data(data, departure_date)


# Bot loop
if __name__ == "__main__":
    logger.info("Starting TCDD Ticket Bot...")

    # Parse and validate routes from environment
    CHECK_ROUTES = parse_routes()

    # Parse and validate dates from environment
    CHECK_DATES = parse_check_dates()
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")

    # Simple loop to check repeatedly
    while True:
        for date in CHECK_DATES:
            for route in CHECK_ROUTES:
                check_train_availability(date, route)

        # Wait before the next request to avoid getting IP banned
        logger.info(
            f"Waiting {CHECK_INTERVAL_SECONDS} seconds before checking again..."
        )
        time.sleep(CHECK_INTERVAL_SECONDS)
