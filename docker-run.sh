#!/bin/bash

# Build and run the Docker container

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Building Docker image...${NC}"
docker build -t ical-to-json-api .

echo -e "${YELLOW}Running Docker container...${NC}"
docker run -d -p 8080:5000 --name ical-to-json-api ical-to-json-api gunicorn --bind 0.0.0.0:5000 application:app

echo -e "${GREEN}Container started!${NC}"
echo -e "The API is available at: ${GREEN}http://localhost:8080${NC}"
echo ""
echo -e "Try it with: ${YELLOW}curl 'http://localhost:8080/api/convert?url=https://calendar.google.com/calendar/ical/en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics'${NC}"
echo ""
echo -e "To stop the container: ${YELLOW}docker stop ical-to-json-api${NC}"
echo -e "To remove the container: ${YELLOW}docker rm ical-to-json-api${NC}"