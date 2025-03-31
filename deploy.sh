#!/bin/bash

# This script runs the application in deployment mode
# It ensures the correct module is used

echo "Starting iCal to JSON API service..."
gunicorn --bind 0.0.0.0:5000 --workers=4 application:app