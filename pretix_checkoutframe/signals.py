import json
import jwt
import secrets
from django.db.models import F
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.middleware import _merge_csp, _parse_csp, _render_csp
from pretix.base.models import Event, Item, Order, QuestionAnswer
from pretix.base.models.items import ItemQuerySet, Question
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings
from pretix.presale.signals import html_head, order_info, process_response
from urllib.parse import urlsplit


@receiver(order_info, dispatch_uid="checkoutframe_order_info")
def order_info(sender: Event, order: Order, request: HttpRequest, **kwargs):
    template = loader.get_template("pretix_checkoutframe/frame.html")

    key = sender.settings.get("checkoutframe_key")
    question = sender.settings.get("checkoutframe_question")
    frame_url = sender.settings.get("checkoutframe_frame_url")
    border_title = sender.settings.get("checkoutframe_border_title")
    items = Item.objects.filter(pk__in=sender.settings.get("checkoutframe_item"))

    answers = (
        QuestionAnswer.objects.filter(
            question=question,
            orderposition__in=order.positions.all(),
            orderposition__item__in=items,
        )
        .annotate(pseudonymization_id=F("orderposition__pseudonymization_id"))
        .only("answer")
    )

    def generate_jwt(answer):
        token = jwt.encode(
            payload={
                "order_code": order.code,
                "pseudonymization_id": answer.pseudonymization_id,
                "answer": answer.answer,
            },
            key=key,
            algorithm="EdDSA",
        )
        return token

    ctx = {
        "elements": [
            {
                "frame_url": frame_url.format(generate_jwt(o)),
                "border_title": border_title.format(o.answer),
            }
            for o in answers.all()
        ]
    }

    return template.render(ctx)


@receiver(nav_event_settings, dispatch_uid="checkoutframe_nav_event_settings")
def nav_event_settings(sender: Event, request: HttpRequest, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": _("Checkout Frame"),
            "url": reverse(
                "plugins:pretix_checkoutframe:control.checkoutframe.settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_checkoutframe"
            and url.url_name == "control.checkoutframe.settings",
        }
    ]


@receiver(html_head, dispatch_uid="checkoutframe_html_head")
def html_head(sender: Event, request: HttpRequest, **kwargs):
    url = resolve(request.path_info)
    if url.url_name != "event.order":
        return None

    nonce = secrets.token_urlsafe(32)
    request.checkoutframe_nonce = nonce
    template = loader.get_template("pretix_checkoutframe/frame_head.html")
    ctx = {
        "frame_height": sender.settings.get("checkoutframe_frame_height"),
        "frame_width": sender.settings.get("checkoutframe_frame_width"),
        "nonce": nonce,
    }

    return template.render(ctx)


@receiver(signal=process_response, dispatch_uid="checkoutframe_process_response")
def signal_process_response(
    sender: Event, request: HttpRequest, response: HttpResponse, **kwargs
):
    url = resolve(request.path_info)
    if url.url_name != "event.order":
        return response

    if "Content-Security-Policy" in response:
        ocsp = _parse_csp(response["Content-Security-Policy"])
    else:
        ocsp = {}

    frame_url = sender.settings.get("checkoutframe_frame_url")
    netloc = urlsplit(frame_url).netloc
    mcsp = {"frame-src": [netloc]}

    if hasattr(request, "checkoutframe_nonce"):
        mcsp["style-src"] = [f"'nonce-{request.checkoutframe_nonce}'"]

    _merge_csp(ocsp, mcsp)

    if ocsp:
        response["Content-Security-Policy"] = _render_csp(ocsp)

    return response


settings_hierarkey.add_type(
    ItemQuerySet,
    lambda v: json.dumps([e.pk for e in v]),
    lambda v: Item.objects.filter(pk__in=json.loads(v)),
)

settings_hierarkey.add_default(
    "checkoutframe_frame_url",
    "https://www.youtube.com/embed/X8PKP0K1Hf8?si=6Zmjos7sVc1TzfsT&mysecrettoken={0}",
    str,
)
settings_hierarkey.add_default("checkoutframe_frame_height", "80vh", str)
settings_hierarkey.add_default("checkoutframe_frame_width", "100%", str)
settings_hierarkey.add_default("checkoutframe_border_title", "Durge {0}", str)
settings_hierarkey.add_default("checkoutframe_item", None, ItemQuerySet)
settings_hierarkey.add_default("checkoutframe_question", None, Question)
