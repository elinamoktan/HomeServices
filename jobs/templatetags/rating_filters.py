from django import template

register = template.Library()

@register.filter
def get_rating_percentage(worker, star_value):
    breakdown = worker.get_rating_breakdown()
    total_ratings = worker.ratings.count()
    
    if total_ratings == 0:
        return 0
    
    star_count = breakdown.get(int(star_value), 0)
    return (star_count / total_ratings) * 100