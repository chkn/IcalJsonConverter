import requests
import urllib.parse
import logging
from datetime import datetime
from icalendar import Calendar, Event
import pytz

def validate_url(url):
    """
    Validate the provided URL
    
    Args:
        url (str): URL to validate
        
    Returns:
        dict: Dictionary containing validation result
    """
    try:
        # Parse the URL to check its validity
        parsed_url = urllib.parse.urlparse(url)
        
        # Check if the URL has a scheme and netloc
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return {
                'valid': False,
                'message': 'Invalid URL format. URL must include scheme (http/https) and domain.'
            }
        
        # Check if the scheme is http or https
        if parsed_url.scheme not in ['http', 'https']:
            return {
                'valid': False,
                'message': 'URL scheme must be http or https'
            }
        
        return {'valid': True}
    except Exception as e:
        logging.error(f"URL validation error: {str(e)}")
        return {
            'valid': False,
            'message': f'URL validation error: {str(e)}'
        }

def fetch_and_parse_ical(url, timeout=10):
    """
    Fetch iCal data from URL and parse it to JSON
    
    Args:
        url (str): URL of the iCal feed
        timeout (int): Request timeout in seconds
        
    Returns:
        dict: Dictionary containing parsed data or error information
    """
    try:
        # Fetch iCal data
        response = requests.get(url, timeout=timeout)
        
        # Check response status
        if response.status_code != 200:
            return {
                'success': False,
                'message': f'Failed to fetch iCal feed. HTTP Status: {response.status_code}',
                'status_code': response.status_code
            }
        
        # Parse iCal data
        try:
            calendar = Calendar.from_ical(response.content)
            
            # Extract calendar information
            calendar_info = {
                'name': str(calendar.get('X-WR-CALNAME', 'Calendar')),
                'description': str(calendar.get('X-WR-CALDESC', '')),
                'timezone': str(calendar.get('X-WR-TIMEZONE', 'UTC')),
            }
            
            # Initialize events list
            events = []
            
            # Process each event in the calendar
            for component in calendar.walk():
                if component.name == "VEVENT":
                    event = {
                        'uid': str(component.get('UID', '')),
                        'summary': str(component.get('SUMMARY', '')),
                        'description': str(component.get('DESCRIPTION', '')),
                        'location': str(component.get('LOCATION', '')),
                        'status': str(component.get('STATUS', '')),
                        'organizer': _parse_organizer(component.get('ORGANIZER', '')),
                        'created': _format_datetime(component.get('CREATED', None)),
                        'last_modified': _format_datetime(component.get('LAST-MODIFIED', None)),
                    }
                    
                    # Handle start time
                    dtstart = component.get('DTSTART', None)
                    if dtstart:
                        event['start'] = _parse_datetime(dtstart)
                    
                    # Handle end time
                    dtend = component.get('DTEND', None)
                    if dtend:
                        event['end'] = _parse_datetime(dtend)
                    
                    # Handle recurrence rule
                    rrule = component.get('RRULE', None)
                    if rrule:
                        event['recurrence'] = _parse_recurrence(rrule)
                    
                    # Add any alarms/reminders
                    alarms = []
                    for subcomponent in component.walk('VALARM'):
                        alarm = {
                            'action': str(subcomponent.get('ACTION', '')),
                            'description': str(subcomponent.get('DESCRIPTION', '')),
                            'trigger': str(subcomponent.get('TRIGGER', '')),
                        }
                        alarms.append(alarm)
                    
                    if alarms:
                        event['alarms'] = alarms
                    
                    events.append(event)
            
            # Prepare final result
            result = {
                'calendar': calendar_info,
                'events': events,
                'event_count': len(events)
            }
            
            return {
                'success': True,
                'data': result
            }
        except Exception as e:
            logging.error(f"iCal parsing error: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to parse iCal data: {str(e)}',
                'status_code': 400
            }
    except requests.Timeout:
        logging.error(f"Request timeout for URL: {url}")
        return {
            'success': False,
            'message': f'Request timed out after {timeout} seconds',
            'status_code': 408
        }
    except requests.RequestException as e:
        logging.error(f"Request error for URL {url}: {str(e)}")
        return {
            'success': False,
            'message': f'Error fetching iCal feed: {str(e)}',
            'status_code': 500
        }

def _format_datetime(dt_value):
    """
    Format datetime value to ISO format string
    
    Args:
        dt_value: icalendar datetime value
        
    Returns:
        str: ISO formatted datetime string or None
    """
    if dt_value is None:
        return None
    
    if hasattr(dt_value, 'dt'):
        dt = dt_value.dt
        if isinstance(dt, datetime):
            # Ensure datetime is timezone aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt.isoformat()
        else:
            # Handle date objects
            return str(dt)
    return str(dt_value)

def _parse_datetime(dt_component):
    """
    Parse datetime component
    
    Args:
        dt_component: icalendar datetime component
        
    Returns:
        dict: Dictionary with formatted datetime and additional information
    """
    result = {
        'datetime': _format_datetime(dt_component)
    }
    
    # Add value type (DATE or DATE-TIME)
    if hasattr(dt_component, 'params') and 'VALUE' in dt_component.params:
        result['value_type'] = str(dt_component.params['VALUE'])
    else:
        # Determine the type based on the parsed result
        dt = dt_component.dt
        result['value_type'] = 'DATE' if not isinstance(dt, datetime) else 'DATE-TIME'
    
    # Add timezone if available
    if hasattr(dt_component, 'params') and 'TZID' in dt_component.params:
        result['timezone'] = str(dt_component.params['TZID'])
    
    return result

def _parse_organizer(organizer):
    """
    Parse organizer component
    
    Args:
        organizer: icalendar organizer component
        
    Returns:
        dict: Dictionary with organizer information or string
    """
    if not organizer:
        return None
    
    # If it's just a string, return as is
    if isinstance(organizer, str):
        return organizer
    
    result = {
        'value': str(organizer)
    }
    
    # Add parameters if available
    if hasattr(organizer, 'params'):
        if 'CN' in organizer.params:
            result['common_name'] = str(organizer.params['CN'])
        if 'EMAIL' in organizer.params:
            result['email'] = str(organizer.params['EMAIL'])
    
    return result

def _parse_recurrence(rrule):
    """
    Parse recurrence rule
    
    Args:
        rrule: icalendar recurrence rule
        
    Returns:
        dict: Dictionary with recurrence information
    """
    if not rrule:
        return None
    
    result = {}
    
    # Convert rrule dictionary to regular dictionary
    for key, value in rrule.items():
        key_str = str(key)
        # Handle list values
        if isinstance(value, list):
            # Join list values with commas
            result[key_str] = [str(v) for v in value]
        else:
            result[key_str] = str(value)
    
    return result
