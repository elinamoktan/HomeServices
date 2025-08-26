import math
from django import template

register = template.Library()

# Haversine formula to calculate the distance between two points
def haversine(lat1, lon1, lat2, lon2):
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of Earth in kilometers is 6371
    km = 6371 * c
    return km

@register.simple_tag
def calculate_distance(worker_lat, worker_lon, customer_lat, customer_lon):
    # Ensure coordinates are not None
    if worker_lat and worker_lon and customer_lat and customer_lon:
        try:
            # Convert latitudes and longitudes to float
            worker_lat, worker_lon = float(worker_lat), float(worker_lon)
            customer_lat, customer_lon = float(customer_lat), float(customer_lon)
            return round(haversine(worker_lat, worker_lon, customer_lat, customer_lon), 2)
        except ValueError:
            return None
    return None

# Template tag to show distance if the user is a customer
@register.simple_tag(takes_context=True)
def distance_if_customer(context, worker):
    user = context['user']

    # Ensure the user is authenticated and is a customer
    if user.is_authenticated and hasattr(user, 'customer'):
        customer = user.customer

        # Check if both worker and customer have latitude and longitude values
        if worker.latitude and worker.longitude and customer.latitude and customer.longitude:
            distance = calculate_distance(worker.latitude, worker.longitude, customer.latitude, customer.longitude)
            if distance == 0:
                return "0 km away"
            return f"{distance} km away" if distance else "Distance unavailable"
    
    return ""
