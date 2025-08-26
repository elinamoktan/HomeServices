# custom_tags.py
from django import template

register = template.Library()

@register.filter
def times(value):
    try:
        value = int(value)
    except (ValueError, TypeError):
        value = 0
    return range(value)
