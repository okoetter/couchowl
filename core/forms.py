from django.forms.renderers import DjangoTemplates


class FormRenderer(DjangoTemplates):
    """Renders form fields with watchit's own field template (core/templates/forms/field.html).

    The Django admin uses its own templates and is not affected.
    """

    field_template_name = "forms/field.html"
