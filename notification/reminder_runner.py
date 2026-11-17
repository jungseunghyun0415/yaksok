
import json
from datetime import datetime
from pathlib import Path

from discord_notify import send_reminder
def check_medication_reminders():
    # Find the medicines.json file
    project_folder = Path(__file__).parent.parent
    json_file = project_folder / "data" / "medicines.json"

    # Load medicine information
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Get the current time
    current_time = datetime.now().strftime("%H:%M")
    # Check every registered medicine
    for medicine in data["medicines"]:
        medicine_name = medicine["name"]
        scheduled_times = medicine["times"]

        # Check whether this medicine is due now
        if current_time in scheduled_times:
            send_reminder(
                medicine_name=medicine_name,
                dosage="Not specified",
                scheduled_time=current_time
            )
            print(f"Reminder sent for {medicine_name}")


if __name__ == "__main__":
    check_medication_reminders()
