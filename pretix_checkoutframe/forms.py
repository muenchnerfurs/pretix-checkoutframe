from django import forms
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm
from pretix.base.models import Question, Item


class CheckoutFrameSettingsForm(SettingsForm):
    checkoutframe_frame_url = forms.CharField(
        label=_("Url to be used inside the frame"),
    )

    checkoutframe_frame_height = forms.CharField(
        label=_("Height of the frame"),
    )

    checkoutframe_frame_width = forms.CharField(
        label=_("Width of the frame"),
    )

    checkoutframe_border_title = forms.CharField(
        label=_("Title of the border"),
    )

    checkoutframe_item = forms.ModelMultipleChoiceField(
        label=_("Items for which to display the checkoutframe"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "scrolling-multiple-choice"}),
        queryset=Item.objects.none(),
    )

    checkoutframe_question = forms.ModelChoiceField(
        label=_("Question to use in border title"),
        queryset=Question.objects.none(),
    )

    checkoutframe_key = forms.CharField(
        label=_("Checkout frame key"),
        help_text=_("Must be a valid ed25519 key in pem format"),
        widget=forms.Textarea,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["checkoutframe_item"].queryset = self.obj.items
        self.fields["checkoutframe_question"].queryset = self.obj.questions
