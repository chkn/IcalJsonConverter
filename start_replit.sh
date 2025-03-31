#!/bin/bash

# This script is specifically optimized for Replit deployment
# It addresses the "ModuleNotFoundError: No module named 'application'" issue

echo "Starting iCal to JSON API service on Replit..."
gunicorn --bind 0.0.0.0:5000 --workers=2 application:app