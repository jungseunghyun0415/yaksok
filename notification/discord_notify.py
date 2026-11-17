
import requests
import os


def send_reminder(medicine_name, dosage, scheduled_time):

    # Get the Discord webhook URL securely
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        raise ValueError("Discord webhook URL is missing.")

    # Create the reminder message
    message = {
        "embeds": [
            {
                "title": "💊 Yaksok Medication Reminder",
                "description": "It is time to take your medication!",
                "fields": [
                    {
                        "name": "Medicine",
                        "value": medicine_name,
                        "inline": True
                    },
                    {
                        "name": "Dosage",
                        "value": dosage,
                        "inline": True
                    },
                    {
                        "name": "Scheduled Time",
                        "value": scheduled_time,
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Please follow your prescribed instructions."
                }
            }
        ]
    }

    # Send the message to Discord
    response = requests.post(
        webhook_url,
        json=message,
        timeout=15
    )

    # Check whether the message was sent successfully
    response.raise_for_status()

    print("Medication reminder sent successfully!")
