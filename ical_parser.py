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
            
            # First pass: collect all events with their properties
            events_by_uid = {}
            
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
                        'related_to': str(component.get('RELATED-TO', '')),
                        'relationship_type': str(component.get('RELTYPE', '')),
                        'subevents': []  # Will store child events
                    }
                    
                    # Extract RELATED-TO parameter if it exists (this may indicate a parent-child relationship)
                    related_to = component.get('RELATED-TO', None)
                    if related_to:
                        event['related_to'] = str(related_to)
                        # Get relationship type if available
                        if hasattr(related_to, 'params') and 'RELTYPE' in related_to.params:
                            event['relationship_type'] = str(related_to.params['RELTYPE'])
                    
                    # Handle any custom 'parent_uid' property that might be in the feed
                    parent_uid = component.get('X-PARENT-UID', component.get('PARENT-UID', None))
                    if parent_uid:
                        event['parent_uid'] = str(parent_uid)
                    
                    # Handle start time
                    dtstart = component.get('DTSTART', None)
                    if dtstart:
                        event['start'] = _parse_datetime(dtstart)
                        event['start_dt'] = dtstart.dt  # Store actual datetime for comparison
                    
                    # Handle end time
                    dtend = component.get('DTEND', None)
                    if dtend:
                        event['end'] = _parse_datetime(dtend)
                        event['end_dt'] = dtend.dt  # Store actual datetime for comparison
                    
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
                    
                    # Store event by UID for later reference
                    events_by_uid[event['uid']] = event
            
            # Second pass: identify parent-child relationships and organize events
            organized_events = []
            processed_uids = set()  # Track which events have been processed
            
            # First check for explicit parent-child relationships via RELATED-TO or similar properties
            for uid, event in events_by_uid.items():
                # Skip if already processed as a child
                if uid in processed_uids:
                    continue
                
                # If this event is related to another event, it might be a child
                if 'related_to' in event and event['related_to'] and event['related_to'] in events_by_uid:
                    parent_event = events_by_uid[event['related_to']]
                    parent_event['subevents'].append(event)
                    processed_uids.add(uid)
                    continue
                
                # If this event has an explicit parent_uid property
                if 'parent_uid' in event and event['parent_uid'] and event['parent_uid'] in events_by_uid:
                    parent_event = events_by_uid[event['parent_uid']]
                    parent_event['subevents'].append(event)
                    processed_uids.add(uid)
                    continue
            
            # Then try to infer parent-child relationships based on time containment
            for uid, event in events_by_uid.items():
                # Skip if already processed as a child
                if uid in processed_uids:
                    continue
                
                # Check if this event's time range contains other events
                if 'start_dt' in event and 'end_dt' in event:
                    for other_uid, other_event in events_by_uid.items():
                        if uid == other_uid or other_uid in processed_uids:
                            continue
                        
                        # Skip if either event is missing datetime info
                        if 'start_dt' not in other_event or 'end_dt' not in other_event:
                            continue
                            
                        # Handle type compatibility - convert dates to datetimes if needed
                        try:
                            # For comparison, convert date to datetime if needed
                            event_start = event['start_dt']
                            event_end = event['end_dt']
                            other_start = other_event['start_dt']
                            other_end = other_event['end_dt']
                            
                            # Convert date objects to datetime objects at midnight
                            if not isinstance(event_start, datetime):
                                event_start = datetime.combine(event_start, datetime.min.time())
                                event_start = event_start.replace(tzinfo=pytz.UTC)
                            if not isinstance(event_end, datetime):
                                event_end = datetime.combine(event_end, datetime.min.time())
                                event_end = event_end.replace(tzinfo=pytz.UTC)
                            if not isinstance(other_start, datetime):
                                other_start = datetime.combine(other_start, datetime.min.time())
                                other_start = other_start.replace(tzinfo=pytz.UTC)
                            if not isinstance(other_end, datetime):
                                other_end = datetime.combine(other_end, datetime.min.time())
                                other_end = other_end.replace(tzinfo=pytz.UTC)
                            
                            # Check if other event is within this event's time range
                            if (event_start <= other_start and event_end >= other_end):
                                
                                # If the time ranges match exactly, compare summary/title length
                                # Longer titles often indicate more specific subevents
                                if (event_start == other_start and event_end == other_end):
                                    if len(other_event['summary']) > len(event['summary']):
                                        # Skip containment for equal time ranges with longer summary
                                        continue
                                
                                # Add this event as a subevent
                                event['subevents'].append(other_event)
                                processed_uids.add(other_uid)
                        except Exception as e:
                            # Log but continue if there's an error comparing dates
                            logging.warning(f"Error comparing event dates: {str(e)}")
            
            # Prepare the final event list, keeping only top-level events
            for uid, event in events_by_uid.items():
                if uid not in processed_uids:
                    # Clean up temporary attributes before adding to the final list
                    event.pop('start_dt', None)
                    event.pop('end_dt', None)
                    
                    # Remove empty properties for cleaner output
                    if not event['related_to']:
                        event.pop('related_to', None)
                    if not event['relationship_type']:
                        event.pop('relationship_type', None)
                    if not event['subevents']:
                        event.pop('subevents', None)
                    
                    # Clean up subevents too
                    if 'subevents' in event:
                        for subevent in event['subevents']:
                            subevent.pop('start_dt', None)
                            subevent.pop('end_dt', None)
                            if not subevent.get('related_to', ''):
                                subevent.pop('related_to', None)
                            if not subevent.get('relationship_type', ''):
                                subevent.pop('relationship_type', None)
                            subevent.pop('subevents', None)  # Don't need nested subevents
                    
                    organized_events.append(event)
            
            # Prepare final result
            result = {
                'calendar': calendar_info,
                'events': organized_events,
                'event_count': len(organized_events),
                'total_events': len(events_by_uid)  # Total including subevents
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
