from django import template

register = template.Library()

@register.simple_tag
def noop_custom_tag():
    """
    Minimal placeholder tag so `{% load custom_tags %}` succeeds.
    Replace/add real tags/filters used by your templates here.
    """
    return ''
    
@register.filter
def noop_filter(value):
    return value