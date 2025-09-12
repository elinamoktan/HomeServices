import math
from django import template

register = template.Library()

# Haversine formula to calculate the distance between two points (lat/lon in degrees)
def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate great-circle distance between two points on Earth (in kilometers).
    Inputs are in degrees, conversion to radians happens inside.
    """
    try:
        # Check for None values
        if None in (lat1, lon1, lat2, lon2):
            return float('inf')
        
        # Convert to floats
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        
        # Validate coordinate ranges
        if not (-90 <= lat1 <= 90) or not (-180 <= lon1 <= 180) or \
           not (-90 <= lat2 <= 90) or not (-180 <= lon2 <= 180):
            return float('inf')
        
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Differences
        dlon = lon2 - lon1
        dlat = lat2 - lat1

        # Haversine formula
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Radius of Earth in kilometers
        km = 6371 * c
        return km
        
    except (ValueError, TypeError):
        return float('inf')

@register.simple_tag
def calculate_distance(worker_lat, worker_lon, customer_lat, customer_lon):
    """
    Calculate distance between worker and customer (in km).
    Ensures values are floats before calling haversine.
    """
    try:
        if worker_lat is not None and worker_lon is not None and customer_lat is not None and customer_lon is not None:
            distance = haversine(worker_lat, worker_lon, customer_lat, customer_lon)
            if distance != float('inf'):
                return round(distance, 2)
    except (ValueError, TypeError):
        pass
    return None

@register.simple_tag(takes_context=True)
def distance_if_customer(context, worker):
    """
    Show distance between worker and customer if logged-in user is a customer.
    """
    user = context['user']

    if user.is_authenticated and hasattr(user, 'customer'):
        customer = user.customer

        if worker.latitude and worker.longitude and customer.latitude and customer.longitude:
            distance = calculate_distance(worker.latitude, worker.longitude, customer.latitude, customer.longitude)
            if distance is not None:
                if distance == 0:
                    return "0 km away"
                return f"{distance} km away"
            return "Distance unavailable"

    return ""