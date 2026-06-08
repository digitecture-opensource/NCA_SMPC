from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allow dict lookup by variable key in templates: {{ mydict|get_item:key }}"""
    if dictionary is None:
        return ""
    val = dictionary.get(key, "")
    if val is None:
        return ""
    return val
