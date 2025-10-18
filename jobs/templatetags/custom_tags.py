from django import template

register = template.Library()

@register.filter
def bayesian_average(avg_rating, total_ratings):
    """
    Calculate Bayesian average rating
    Formula: (avg_rating * total_ratings + C * m) / (total_ratings + C)
    Where C is confidence factor and m is minimum expected rating
    """
    if not avg_rating or not total_ratings:
        return 0
    
    C = 3.0  # Confidence factor
    m = 2.5  # Minimum expected rating (midpoint of 1-5 scale)
    
    try:
        bayesian_avg = (float(avg_rating) * int(total_ratings) + C * m) / (int(total_ratings) + C)
        return round(bayesian_avg, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def avg_rating(ratings):
    """Calculate average rating from a queryset of ratings"""
    if not ratings:
        return 0
    try:
        total = sum(rating.rating for rating in ratings)
        return total / len(ratings)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0