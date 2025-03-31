import os
import logging
from flask import Flask, jsonify, request, render_template
from ical_parser import fetch_and_parse_ical, validate_url
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-dev-secret")

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

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500
