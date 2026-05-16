from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from pretix.base.forms import SettingsForm
from pretix.base.models import Item, Question


class CollapsibleTextarea(forms.Textarea):
    """
    Textarea hidden behind a <details> disclosure.

    This is only visual concealment, not a security boundary.
    """

    def render(self, name, value, attrs=None, renderer=None):
        textarea = super().render(name, value, attrs, renderer)
        return format_html(
            """
            <details>
                <summary>{}</summary>
                <div style="margin-top: 10px;">
                    {}
                </div>
            </details>
            """,
            _("Show/change private key"),
            textarea,
        )


class CheckoutFrameSettingsForm(SettingsForm):
    checkoutframe_frame_url = forms.CharField(
        label=_("Url to be used inside the frame"),
    )

    checkoutframe_frame_width = forms.CharField(
        label=_("Width of the frame"),
        help_text=_("Examples: 100%, 800px, 80vw"),
    )

    checkoutframe_frame_height = forms.CharField(
        label=_("Height of the frame"),
        required=False,
        help_text=_(
            "Examples: 80vh, 600px. Leave empty if you use an aspect ratio."
        ),
    )

    checkoutframe_aspect_ratio = forms.CharField(
        label=_("Aspect ratio"),
        required=False,
        help_text=_(
            "Optional. Examples: 16 / 9, 4 / 3, 1 / 1. "
            "If set, the frame height is calculated from the width."
        ),
    )

    checkoutframe_border_title = forms.CharField(
        label=_("Title of the border"),
    )

    checkoutframe_item = forms.ModelMultipleChoiceField(
        label=_("Items for which to display the checkoutframe"),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "scrolling-multiple-choice"}
        ),
        queryset=Item.objects.none(),
    )

    checkoutframe_question = forms.ModelChoiceField(
        label=_("Question to use in border title"),
        queryset=Question.objects.none(),
    )

    checkoutframe_key = forms.CharField(
        label=_("Checkout frame private key"),
        required=False,
        help_text=_(
            "If a private key is already configured, this field is intentionally "
            "left empty. Paste a new prime256v1 EC private key in PEM format only "
            "if you want to replace it."
        ),
        widget=CollapsibleTextarea(
            attrs={
                "rows": 8,
                "spellcheck": "false",
                "autocomplete": "off",
                "autocapitalize": "off",
                "placeholder": _("Leave empty to keep the existing private key."),
                "style": "font-family: monospace;",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["checkoutframe_item"].queryset = self.obj.items
        self.fields["checkoutframe_question"].queryset = self.obj.questions

        existing_key = self._get_existing_checkoutframe_key()

        # Never render the stored private key back into the page.
        self.initial["checkoutframe_key"] = ""

        if existing_key:
            self.fields["checkoutframe_key"].help_text = _(
                "A private key is already configured. This field is intentionally "
                "left empty. Paste a new prime256v1 EC private key in PEM format "
                "only if you want to replace it."
            )
            self.fields["checkoutframe_key"].widget.attrs["placeholder"] = _(
                "Private key already configured. Leave empty to keep it."
            )
        else:
            self.fields["checkoutframe_key"].help_text = _(
                "Paste a prime256v1 EC private key in PEM format."
            )
            self.fields["checkoutframe_key"].widget.attrs["placeholder"] = _(
                "Paste private key here."
            )

    def _get_existing_checkoutframe_key(self):
        settings_obj = getattr(self, "settings", None)

        if settings_obj is None:
            obj = getattr(self, "obj", None)
            settings_obj = getattr(obj, "settings", None)

        if settings_obj is None:
            return ""

        return settings_obj.get("checkoutframe_key", "") or ""

    def clean_checkoutframe_aspect_ratio(self):
        value = self.cleaned_data.get("checkoutframe_aspect_ratio", "") or ""
        value = value.strip()

        if not value:
            return ""

        normalized = value.replace(" ", "")

        if "/" not in normalized:
            raise ValidationError(
                _("Aspect ratio must look like 16 / 9, 4 / 3, or 1 / 1.")
            )

        width, height = normalized.split("/", 1)

        try:
            width = float(width)
            height = float(height)
        except ValueError:
            raise ValidationError(
                _("Aspect ratio must contain two numbers, e.g. 16 / 9.")
            )

        if width <= 0 or height <= 0:
            raise ValidationError(
                _("Aspect ratio numbers must be greater than zero.")
            )

        # Store in a clean CSS-compatible format.
        return f"{width:g} / {height:g}"

    def clean_checkoutframe_key(self):
        value = self.cleaned_data.get("checkoutframe_key", "") or ""
        value = value.strip()

        existing_key = self._get_existing_checkoutframe_key()

        # Empty field means: keep the current private key.
        if not value:
            return existing_key

        # Helpful if the key came from an env var with literal "\n".
        value = value.replace("\\n", "\n")

        try:
            key = serialization.load_pem_private_key(
                value.encode("utf-8"),
                password=None,
            )
        except Exception:
            raise ValidationError(
                _(
                    "This is not a valid unencrypted EC private key in PEM format."
                )
            )

        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValidationError(
                _("The key must be an EC private key, not an RSA or public key.")
            )

        if not isinstance(key.curve, ec.SECP256R1):
            raise ValidationError(
                _("The key must use the prime256v1 / secp256r1 curve.")
            )

        return value