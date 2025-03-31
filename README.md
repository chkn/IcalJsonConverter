# iCal to JSON Converter API

A REST API that fetches iCal feeds from URLs and converts them to a structured JSON format.

## Features

- Convert iCal feeds to structured JSON
- Support for calendar metadata and properties
- Detailed event information including start, end times, location, and recurrence
- Hierarchical event structure with parent events and subevents
- Smart detection of event relationships based on time containment
- Error handling for invalid URLs and malformed iCal data
- Configurable request timeout

## Running with Docker

### Using Docker Compose (Recommended)

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd ical-to-json-api
   ```

2. (Optional) Create a `.env` file to set environment variables:
   ```bash
   SESSION_SECRET=your-secure-secret-key
   ```

3. Build and start the container:
   ```bash
   docker-compose up -d
   ```

4. The API will be available at http://localhost:5000

### Using Docker directly

1. Build the Docker image:
   ```bash
   docker build -t ical-to-json-api .
   ```

2. Run the container:
   ```bash
   docker run -d -p 5000:5000 --name ical-to-json-api ical-to-json-api
   ```

3. The API will be available at http://localhost:5000

## API Usage

### Converting an iCal feed to JSON

```
GET /api/convert?url=https://example.com/calendar.ics&timeout=10
```

#### Query Parameters

- `url` (required): URL of the iCal feed to convert
- `timeout` (optional): Request timeout in seconds (default: 10, max: 60)

#### Example Response

```json
{
  "calendar": {
    "name": "My Calendar",
    "description": "My personal calendar",
    "timezone": "America/New_York"
  },
  "events": [
    {
      "uid": "event-123@example.com",
      "summary": "Team Meeting",
      "description": "Weekly team meeting",
      "location": "Conference Room A",
      "start": {
        "datetime": "2023-05-10T10:00:00-04:00",
        "value_type": "DATE-TIME",
        "timezone": "America/New_York"
      },
      "end": {
        "datetime": "2023-05-10T11:00:00-04:00",
        "value_type": "DATE-TIME",
        "timezone": "America/New_York"
      },
      "subevents": [
        {
          "uid": "subevent-456@example.com",
          "summary": "Sprint Planning",
          "description": "Planning session for next sprint",
          "start": {
            "datetime": "2023-05-10T10:00:00-04:00",
            "value_type": "DATE-TIME",
            "timezone": "America/New_York"
          },
          "end": {
            "datetime": "2023-05-10T10:30:00-04:00",
            "value_type": "DATE-TIME",
            "timezone": "America/New_York"
          }
        }
      ]
    }
  ],
  "event_count": 1,
  "total_events": 2
}
```

## Development

### Local Setup

1. Install requirements:
   ```bash
   pip install -r docker-requirements.txt
   ```

2. Run the application:
   ```bash
   python main.py
   ```

3. The app will be available at http://localhost:5000

## License

MIT