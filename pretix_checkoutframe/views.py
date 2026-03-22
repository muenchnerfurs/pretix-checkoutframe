from django.urls import reverse
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin

from .forms import CheckoutFrameSettingsForm


class SettingsView(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = CheckoutFrameSettingsForm
    template_name = "pretix_checkoutframe/settings.html"

    def get_success_url(self):
        return reverse(
            "plugins:pretix_checkoutframe:control.checkoutframe.settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
