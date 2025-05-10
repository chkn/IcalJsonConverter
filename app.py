import os
import logging
import json
import re
from flask import Flask, jsonify, request, render_template
from ical_parser import fetch_and_parse_ical, validate_url
import urllib.parse
import requests

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-dev-secret")

# Glide API constants
GLIDE_TRIPS_TABLE_ID = "1fbe5ef8-ceb8-4272-98fa-5c36a79a8eb3"
GLIDE_TRIPS_API_URL = f"https://api.glideapps.com/tables/{GLIDE_TRIPS_TABLE_ID}"
GLIDE_EVENTS_TABLE_ID = "95fd8fa7-c02b-4cf3-97cd-ca3311f0054e"
GLIDE_EVENTS_API_URL = f"https://api.glideapps.com/tables/{GLIDE_EVENTS_TABLE_ID}"

# Pattern to extract type from description [Type]
TYPE_PATTERN = re.compile(r'\[(.*?)\]')


@app.route('/')
def index():
    """Render the home page with API documentation"""
    return render_template('index.html')


@app.route('/documentation')
def documentation():
    """Render the detailed API documentation"""
    return render_template('documentation.html')


@app.route('/api/convert', methods=['GET'])
def convert_ical_to_json():
    """
    API endpoint to convert iCal format to JSON
    
    Query parameters:
    - url: The URL of the iCal feed to convert
    - timeout (optional): Timeout in seconds for the request (default: 10)
    """
    # Get URL parameter
    url = request.args.get('url')

    # Get optional timeout parameter, default to 10 seconds
    try:
        timeout = int(request.args.get('timeout', 10))
        if timeout <= 0 or timeout > 60:
            return jsonify(
                {"error": "Timeout must be between 1 and 60 seconds"}), 400
    except ValueError:
        return jsonify({"error": "Timeout must be a valid integer"}), 400

    # Validate URL
    if not url:
        return jsonify({"error": "Missing required parameter: url"}), 400

    url_validation_result = validate_url(url)
    if not url_validation_result['valid']:
        return jsonify({"error": url_validation_result['message']}), 400

    # Fetch and parse iCal
    result = fetch_and_parse_ical(url, timeout)

    # Return appropriate response based on result
    if result['success']:
        return jsonify(result['data'])
    else:
        status_code = result.get('status_code', 500)
        return jsonify({"error": result['message']}), status_code


def extract_type_from_description(description):
    """
    Extract type from description field using [Type] pattern
    
    Args:
        description (str): Event description
        
    Returns:
        str: Extracted type or empty string if not found
    """
    if not description:
        return ""

    match = TYPE_PATTERN.search(description)
    if match:
        return match.group(1).strip()
    return ""


def sync_table_with_etag_handling(api_url, headers, rows_to_update):
    """
    Sync data with Glide API table with ETag-based concurrency control
    
    Args:
        api_url (str): Glide API table URL
        headers (dict): Headers for API requests
        rows_to_update (list): Rows to update or add
        
    Returns:
        tuple: (success, message, row_count)
    """
    max_retries = 3
    retries = 0

    while retries < max_retries:
        try:
            # Get current data with ETag
            response = requests.get(f"{api_url}/rows", headers=headers)
            response.raise_for_status()

            etag = response.headers.get('ETag')
            if not etag:
                logging.warning("No ETag received from Glide API")

            current_rows = response.json().get('data', [])
            logging.debug(
                f"Received {len(current_rows)} rows from Glide API table {api_url}"
            )

            # Create a copy of all existing rows to preserve them
            final_rows_by_uid = {
                row.get('uid'): row.copy()
                for row in current_rows if 'uid' in row
            }

            # Update existing rows or add new rows
            for row in rows_to_update:
                uid = row.get('uid')
                if uid in final_rows_by_uid:
                    # Update existing row while preserving fields not in the update
                    final_rows_by_uid[uid].update(row)
                else:
                    # This is a new row
                    final_rows_by_uid[uid] = row

            # Convert dictionary to list for the API
            final_rows = list(final_rows_by_uid.values())

            # Add If-Match header if we have an ETag
            put_headers = headers.copy()
            if etag:
                # Strip any leading W/ from the ETag value
                etag = etag.lstrip('W/')
                put_headers['If-Match'] = etag

            # Update table
            update_payload = {"rows": final_rows}
            put_response = requests.put(api_url,
                                        headers=put_headers,
                                        json=update_payload)

            # If we get a 412 (Precondition Failed), retry the operation
            if put_response.status_code == 412:
                logging.warning(
                    "Optimistic concurrency conflict detected, retrying...")
                retries += 1
                continue
            elif put_response.status_code != 200:
                response_body = put_response.json()
                message = f"Unexpected response from Glide API: {response_body}"
                logging.error(message)
                return False, message, 0

            # For other status codes, raise exception
            put_response.raise_for_status()

            return True, f"Successfully synced {len(final_rows)} rows", len(
                final_rows)

        except requests.RequestException as e:
            # Only retry on optimistic concurrency conflicts
            response = getattr(e, 'response', None)
            status_code = None
            if response is not None:
                status_code = getattr(response, 'status_code', None)

            if retries >= max_retries - 1 or status_code != 412:
                logging.error(f"API request error: {str(e)}")
                return False, f"Error communicating with Glide API: {str(e)}", 0

            retries += 1

    return False, "Maximum retries exceeded for optimistic concurrency control", 0


@app.route('/api/sync', methods=['POST'])
def sync_ical_to_glide():
    """
    API endpoint to sync iCal events with Glide API
    
    Request parameters:
    - url: The URL of the iCal feed to sync (in request body)
    - Authorization: Bearer token in the header for Glide API authentication
    - timeout (optional): Timeout in seconds for the request (default: 10)
    """
    # Get Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({
            "error":
            "Missing or invalid Authorization header. Must be in format: 'Bearer YOUR_TOKEN'"
        }), 401

    bearer_token = auth_header.split(' ')[1]

    # Get request data
    data = request.json
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    # Get required parameters
    url = data.get('url')

    # Validate required parameters
    if not url:
        return jsonify({"error": "Missing required parameter: url"}), 400

    # Get optional timeout parameter, default to 10 seconds
    try:
        timeout = int(data.get('timeout', 10))
        if timeout <= 0 or timeout > 60:
            return jsonify(
                {"error": "Timeout must be between 1 and 60 seconds"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Timeout must be a valid integer"}), 400

    # Validate URL
    url_validation_result = validate_url(url)
    if not url_validation_result['valid']:
        return jsonify({"error": url_validation_result['message']}), 400

    # Fetch and parse iCal
    ical_result = fetch_and_parse_ical(url, timeout)

    if not ical_result['success']:
        status_code = ical_result.get('status_code', 500)
        return jsonify({"error": ical_result['message']}), status_code

    # If successful, attempt to sync with Glide API
    try:
        # Setup headers for Glide API requests
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }

        # Process top-level events (trips)
        trips_to_update = []
        events_to_update = []

        # Organize events by trip and subevents
        events_data = ical_result['data']['events']
        logging.debug(f"Processing {len(events_data)} events from iCal")

        for event in events_data:
            # Skip events without UIDs
            if not event.get('uid'):
                continue

            # Process main trip event
            event_uid = event.get('uid')
            event_name = event.get('summary', '')
            event_location = event.get('location', '')

            # Get start and end times
            start_date = None
            end_date = None

            if 'start' in event and 'datetime' in event['start']:
                start_date = event['start']['datetime']

            if 'end' in event and 'datetime' in event['end']:
                end_date = event['end']['datetime']

            # Create trip row
            trip_row = {
                "uid": event_uid,
                "name": event_name,
                "ZS0Be": event_location
            }

            if start_date:
                trip_row["startDate"] = start_date
            if end_date:
                trip_row["endDate"] = end_date

            trips_to_update.append(trip_row)

            # Process subevents
            if 'subevents' in event and event['subevents']:
                for subevent in event['subevents']:
                    if not subevent.get('uid'):
                        continue

                    subevent_uid = subevent.get('uid')
                    subevent_summary = subevent.get('summary', '')
                    subevent_description = subevent.get('description', '')
                    subevent_location = subevent.get('location', '')

                    # Extract event type from description [Type]
                    event_type = extract_type_from_description(
                        subevent_description)

                    # Get start and end times
                    subevent_start = None
                    subevent_end = None

                    if 'start' in subevent and 'datetime' in subevent['start']:
                        subevent_start = subevent['start']['datetime']

                    if 'end' in subevent and 'datetime' in subevent['end']:
                        subevent_end = subevent['end']['datetime']

                    # Create event row
                    event_row = {
                        "uid": subevent_uid,
                        "tripUID": event_uid,
                        "summary": subevent_summary
                    }

                    if event_type:
                        event_row["type"] = event_type
                    if subevent_location:
                        event_row["location"] = subevent_location
                    if subevent_start:
                        event_row["startDate"] = subevent_start
                    if subevent_end:
                        event_row["endDate"] = subevent_end

                    events_to_update.append(event_row)

        # Sync trips table
        trips_success, trips_message, trips_count = sync_table_with_etag_handling(
            GLIDE_TRIPS_API_URL, headers, trips_to_update)

        # Sync events table
        events_success, events_message, events_count = sync_table_with_etag_handling(
            GLIDE_EVENTS_API_URL, headers, events_to_update)

        # Prepare response
        response_data = {
            "success": trips_success and events_success,
            "trips": {
                "success": trips_success,
                "message": trips_message,
                "synced_count": trips_count
            },
            "events": {
                "success": events_success,
                "message": events_message,
                "synced_count": events_count
            }
        }

        if not response_data["success"]:
            return jsonify(response_data), 500

        return jsonify(response_data)

    except requests.RequestException as e:
        logging.error(f"Glide API request error: {str(e)}")
        return jsonify(
            {"error": f"Error communicating with Glide API: {str(e)}"}), 500
    except Exception as e:
        logging.error(f"Sync error: {str(e)}")
        return jsonify({"error": f"Error during sync process: {str(e)}"}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500
