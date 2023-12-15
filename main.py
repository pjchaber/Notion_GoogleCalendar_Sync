# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
import datetime
import os.path
from pprint import pprint
import logging

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
from notion_client import Client
from config import Config


config = Config('config.json')
notion_secret = config['notion']['secret']
notion_calendar_id = config['notion']['calendar_id']
notion_database_id = config['notion']['database_id']
dry_run = config['dry_run']
working_dir = config['working_dir']
ja = config['notion']['me']
timezone = pytz.timezone(config['timezone'])

notion = Client(auth=notion_secret)  # , log_level=logging.DEBUG)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar'
]


def main():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(config["working_dir"] + 'token.json'):
        creds = Credentials.from_authorized_user_file(config["working_dir"] + 'token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config["working_dir"] + 'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(config["working_dir"] + 'token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)

        qf = {
            "timestamp": "last_edited_time",
            "last_edited_time": {
                "on_or_after": (datetime.datetime.now(tz=timezone) - datetime.timedelta(days=7)).isoformat()
        }}
        notion_results = []
        notion_events = notion.databases.query(
            database_id=config['notion']["database_id"],
            filter=qf)
        print(notion_events.keys())
        print(notion_events["has_more"])
        print(notion_events["next_cursor"])
        notion_results += notion_events["results"]

        while notion_events["has_more"]:
            notion_events = notion.databases.query(
                **{
                    "database_id": config['notion']["database_id"],
                    "start_cursor": notion_events["next_cursor"],
                    "filter": {
                        "timestamp": "last_edited_time",
                        "last_edited_time": {
                            "on_or_after": (datetime.datetime.now(tz=timezone) - datetime.timedelta(days=7)).isoformat()
                        }
                    }
                }
            )
            notion_results += notion_events["results"]

        for notion_event in notion_results:
            properties = notion_event["properties"]
            page_id = notion_event["id"]
            Tytul = properties['Tytuł']['title'][0]['plain_text']
            Data_start = properties['Date']["date"]['start']
            Data_end = properties['Date']["date"]['end'] if properties['Date']["date"]['end'] is not None else Data_start
            CalendarID = properties['GoogleCalendarID']['rich_text'][0]['plain_text'].strip() if len(
                properties['GoogleCalendarID']['rich_text']) > 0 else ""
            Prowadzi = properties['Prowadzi']['formula']['string']
            Rodzaj = properties['Rodzaj']['select']['name']

            LastEditedTime = notion_event['last_edited_time']

            start_all_day = datetime.datetime.fromisoformat(Data_start).time() == datetime.time(0, 0, 0)
            end_all_day = datetime.datetime.fromisoformat(Data_start).time() == datetime.time(0, 0, 0)
            if start_all_day != end_all_day:
                print("Inconsistent information in start and end dates -- one all day and the other not. Ignoring!")
                continue
            all_day = start_all_day

            if CalendarID == "" and (Prowadzi == ja or Rodzaj == "Informacja"):  # Dodaj wydarzenie, którego nie miałem
                print(f"+ {Tytul:40s} | {Data_start} --> {Data_end} ")
                event = {
                    'summary': Tytul,
                    'attendees': [],
                    'reminders': {'useDefault': False, 'overrides': [], },
                }
                if all_day:
                    event['start'] = {'date': Data_start }
                    event['end'] = {
                        'date': (datetime.datetime.fromisoformat(Data_end) + datetime.timedelta(
                        days=1)).date().isoformat()
                    }
                else:
                    event['start'] = {'dateTime': Data_start}
                    event['end'] = {'dateTime': Data_end}
                # pprint(event)

                if not config["dry_run"]:
                    event = service.events().insert(calendarId=config['notion']["calendar_id"], body=event).execute()
                    notion_events = notion.pages.update(
                        **{"page_id": page_id,
                           "properties": {"GoogleCalendarID": {"rich_text": [{"type": "text", "text": {
                               "content": event["id"], "link": None}}]}}})

            elif CalendarID != "" and (Prowadzi == ja or Rodzaj == "Informacja"):  # Modyfikuj wydarzenie, które jest
                google_event = service.events().get(calendarId=config['notion']["calendar_id"], eventId=CalendarID).execute()
                if all_day:
                    if google_event['summary'] == Tytul \
                            and datetime.datetime.fromisoformat(
                        google_event['start']['date']) == datetime.datetime.fromisoformat(Data_start) \
                            and datetime.datetime.fromisoformat(
                        google_event['end']['date']) == datetime.datetime.fromisoformat(Data_end)+datetime.timedelta(
                        days=1) \
                            and google_event['id'] == CalendarID:
                        continue
                elif google_event['summary'] == Tytul \
                        and datetime.datetime.fromisoformat(
                    google_event['start']['dateTime']) == datetime.datetime.fromisoformat(Data_start) \
                        and datetime.datetime.fromisoformat(
                    google_event['end']['dateTime']) == datetime.datetime.fromisoformat(Data_end) \
                        and google_event['id'] == CalendarID:
                    continue

                print(f"M {Tytul:40s} | {Data_start} --> {Data_end} | {CalendarID}")

                google_event['summary'] = Tytul
                google_event['id'] = CalendarID
                if all_day:
                    google_event['start']['date'] = Data_start
                    google_event['end']['date'] = (datetime.datetime.fromisoformat(Data_end) + datetime.timedelta(
                        days=1)).date().isoformat()
                else:
                    google_event['start']['dateTime'] = Data_start
                    google_event['end']['dateTime'] = Data_end
                print(google_event)
                if not config["dry_run"]:
                    updated_event = service.events().update(calendarId=config['notion']["calendar_id"],
                                                            eventId=google_event['id'],
                                                            body=google_event).execute()

            elif CalendarID != "" and not (
                    Prowadzi == ja or Rodzaj == "Informacja"):  # Usuń wydarzenie, które jest wpisane
                google_event = service.events().get(calendarId=config['notion']["calendar_id"], eventId=CalendarID).execute()
                print(f"- {Tytul:40s} | {Data_start} --> {Data_end} | {CalendarID} {google_event}")
                service.events().delete(calendarId=config['notion']["calendar_id"], eventId=CalendarID).execute()
                notion_events = notion.pages.update(
                    **{"page_id": page_id,
                       "properties": {"GoogleCalendarID": {"rich_text": [{"type": "text", "text": {
                           "content": "", "link": None}}]}}})
                # Zaktualizuj pole GoogleCalendarID w Notion

    except HttpError as error:
        print('An error occurred: %s' % error)


if __name__ == '__main__':
    main()
