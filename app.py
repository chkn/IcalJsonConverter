import os
import logging
import json
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
GLIDE_TABLE_ID = "1fbe5ef8-ceb8-4272-98fa-5c36a79a8eb3"
GLIDE_API_BASE_URL = f"https://api.glideapps.com/tables/{GLIDE_TABLE_ID}"

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
            return jsonify({"error": "Timeout must be between 1 and 60 seconds"}), 400
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

@app.route('/api/sync', methods=['POST'])
def sync_ical_to_glide():
    """
    API endpoint to sync iCal events with Glide API
    
    Request parameters:
    - url: The URL of the iCal feed to sync
    - bearer_token: Bearer token for Glide API authentication
    - timeout (optional): Timeout in seconds for the request (default: 10)
    """
    # Get request data
    data = request.json
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400
        
    # Get required parameters
    url = data.get('url')
    bearer_token = data.get('bearer_token')
    
    # Validate required parameters
    if not url:
        return jsonify({"error": "Missing required parameter: url"}), 400
    if not bearer_token:
        return jsonify({"error": "Missing required parameter: bearer_token"}), 400
    
    # Get optional timeout parameter, default to 10 seconds
    try:
        timeout = int(data.get('timeout', 10))
        if timeout <= 0 or timeout > 60:
            return jsonify({"error": "Timeout must be between 1 and 60 seconds"}), 400
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
        
        # Step 1: Fetch current rows from Glide API
        logging.debug(f"Fetching rows from Glide API: {GLIDE_API_BASE_URL}/rows")
        response = requests.get(f"{GLIDE_API_BASE_URL}/rows", headers=headers)
        response.raise_for_status()
        
        current_rows = response.json().get('data', [])
        logging.debug(f"Received {len(current_rows)} rows from Glide API")
        
        # Create a dictionary of existing rows by UID for easier lookup
        existing_rows_by_uid = {row.get('uid'): row for row in current_rows if 'uid' in row}
        
        # Step 2: Convert iCal events to Glide row format
        events = ical_result['data']['events']
        logging.debug(f"Processing {len(events)} events from iCal")
        
        new_rows = []
        for event in events:
            # Skip events without UIDs
            if not event.get('uid'):
                continue
                
            # Extract required fields for Glide
            event_uid = event.get('uid')
            event_name = event.get('summary', '')
            
            # Get start and end times
            start_date = None
            end_date = None
            
            if 'start' in event and 'datetime' in event['start']:
                start_date = event['start']['datetime']
            
            if 'end' in event and 'datetime' in event['end']:
                end_date = event['end']['datetime']
            
            # If this event already exists in Glide, keep the row ID and update fields
            if event_uid in existing_rows_by_uid:
                existing_row = existing_rows_by_uid[event_uid]
                row = {
                    "$rowID": existing_row.get("$rowID"),
                    "uid": event_uid,
                    "name": event_name
                }
                if start_date:
                    row["startDate"] = start_date
                if end_date:
                    row["endDate"] = end_date
                    
                new_rows.append(row)
                # Remove from dictionary to track which events were processed
                existing_rows_by_uid.pop(event_uid)
            else:
                # This is a new event
                row = {
                    "uid": event_uid,
                    "name": event_name
                }
                if start_date:
                    row["startDate"] = start_date
                if end_date:
                    row["endDate"] = end_date
                    
                new_rows.append(row)
        
        # Step 3: Call Glide API to update the table
        update_payload = {"rows": new_rows}
        logging.debug(f"Updating Glide API with {len(new_rows)} rows")
        
        put_response = requests.put(GLIDE_API_BASE_URL, headers=headers, json=update_payload)
        put_response.raise_for_status()
        
        return jsonify({
            "success": True,
            "message": f"Successfully synced {len(new_rows)} events",
            "synced_event_count": len(new_rows),
            "removed_event_count": len(existing_rows_by_uid)
        })
        
    except requests.RequestException as e:
        logging.error(f"Glide API request error: {str(e)}")
        return jsonify({
            "error": f"Error communicating with Glide API: {str(e)}"
        }), 500
    except Exception as e:
        logging.error(f"Sync error: {str(e)}")
        return jsonify({
            "error": f"Error during sync process: {str(e)}"
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500
