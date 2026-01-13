"""
Stripe webhook handlers for subscription events.
"""

import logging
from typing import Dict, Any

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import send_mail

from apps.billing.stripe_client import StripeService
from apps.billing.models import Subscription, Invoice

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle incoming Stripe webhooks.

    Verifies webhook signature and routes to appropriate handler.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload
        logger.error("Invalid webhook payload")
        return HttpResponse(status=400)
    except stripe.SignatureVerificationError:
        # Invalid signature
        logger.error("Invalid webhook signature")
        return HttpResponse(status=400)

    # Get event type
    event_type = event['type']
    event_data = event['data']['object']

    logger.info(f"Processing webhook event: {event_type}")

    # Route to appropriate handler
    handlers = {
        'checkout.session.completed': handle_checkout_completed,
        'customer.subscription.created': handle_subscription_created,
        'customer.subscription.updated': handle_subscription_updated,
        'customer.subscription.deleted': handle_subscription_deleted,
        'invoice.paid': handle_invoice_paid,
        'invoice.payment_failed': handle_invoice_payment_failed,
    }

    handler = handlers.get(event_type)

    if handler:
        try:
            handler(event_data)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            logger.error(f"Error handling webhook {event_type}: {e}", exc_info=True)
            # Return 200 to prevent Stripe from retrying
            return JsonResponse({'status': 'error', 'message': str(e)}, status=200)
    else:
        # Unhandled event type
        logger.info(f"Unhandled webhook event type: {event_type}")
        return JsonResponse({'status': 'ignored'})


@transaction.atomic
def handle_checkout_completed(session: Dict[str, Any]) -> None:
    """
    Handle checkout.session.completed event.

    Creates or updates subscription when checkout is completed.
    """
    logger.info(f"Handling checkout.session.completed: {session['id']}")

    # If this is a subscription checkout
    if session.get('mode') == 'subscription':
        subscription_id = session.get('subscription')

        if subscription_id:
            # Retrieve full subscription details from Stripe
            stripe_subscription = stripe.Subscription.retrieve(subscription_id)
            StripeService.sync_subscription(stripe_subscription)


@transaction.atomic
def handle_subscription_created(subscription: Dict[str, Any]) -> None:
    """
    Handle customer.subscription.created event.

    Creates subscription record in database.
    """
    logger.info(f"Handling customer.subscription.created: {subscription['id']}")

    try:
        StripeService.sync_subscription(subscription)
    except Exception as e:
        logger.error(f"Error creating subscription {subscription['id']}: {e}")
        raise


@transaction.atomic
def handle_subscription_updated(subscription: Dict[str, Any]) -> None:
    """
    Handle customer.subscription.updated event.

    Updates subscription status, period, and other details.
    """
    logger.info(f"Handling customer.subscription.updated: {subscription['id']}")

    try:
        db_subscription = StripeService.sync_subscription(subscription)

        # Send notification if subscription status changed to specific states
        if db_subscription.status in [Subscription.Status.CANCELLED, Subscription.Status.PAST_DUE]:
            notify_subscription_status_change(db_subscription)

    except Exception as e:
        logger.error(f"Error updating subscription {subscription['id']}: {e}")
        raise


@transaction.atomic
def handle_subscription_deleted(subscription: Dict[str, Any]) -> None:
    """
    Handle customer.subscription.deleted event.

    Marks subscription as cancelled.
    """
    logger.info(f"Handling customer.subscription.deleted: {subscription['id']}")

    try:
        db_subscription = Subscription.objects.get(
            stripe_subscription_id=subscription['id']
        )
        db_subscription.status = Subscription.Status.CANCELLED
        db_subscription.save()

        # Notify company owner
        notify_subscription_cancelled(db_subscription)

    except Subscription.DoesNotExist:
        logger.error(f"Subscription {subscription['id']} not found in database")
        raise


@transaction.atomic
def handle_invoice_paid(invoice: Dict[str, Any]) -> None:
    """
    Handle invoice.paid event.

    Creates or updates invoice record and marks as paid.
    """
    logger.info(f"Handling invoice.paid: {invoice['id']}")

    try:
        # Only process invoices with subscriptions
        if invoice.get('subscription'):
            db_invoice = StripeService.sync_invoice(invoice)

            # Send receipt email
            send_invoice_receipt(db_invoice)

    except Exception as e:
        logger.error(f"Error processing paid invoice {invoice['id']}: {e}")
        raise


@transaction.atomic
def handle_invoice_payment_failed(invoice: Dict[str, Any]) -> None:
    """
    Handle invoice.payment_failed event.

    Updates invoice status and notifies company.
    """
    logger.info(f"Handling invoice.payment_failed: {invoice['id']}")

    try:
        # Only process invoices with subscriptions
        if invoice.get('subscription'):
            db_invoice = StripeService.sync_invoice(invoice)

            # Notify company of failed payment
            notify_payment_failed(db_invoice)

    except Exception as e:
        logger.error(f"Error processing failed invoice {invoice['id']}: {e}")
        raise


# Notification helper functions

def notify_subscription_status_change(subscription: Subscription) -> None:
    """
    Send notification about subscription status change.

    Args:
        subscription: Subscription that changed status
    """
    company = subscription.company
    owner_email = company.owner.email

    subject = f"Subscription Status Update - {company.name}"
    message = (
        f"Your subscription status has changed to: {subscription.get_status_display()}\n\n"
        f"Plan: {subscription.plan.name}\n"
        f"Status: {subscription.get_status_display()}\n"
    )

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner_email],
            fail_silently=False,
        )
        logger.info(f"Sent status change notification to {owner_email}")
    except Exception as e:
        logger.error(f"Failed to send status notification: {e}")


def notify_subscription_cancelled(subscription: Subscription) -> None:
    """
    Send notification about subscription cancellation.

    Args:
        subscription: Cancelled subscription
    """
    company = subscription.company
    owner_email = company.owner.email

    subject = f"Subscription Cancelled - {company.name}"
    message = (
        f"Your subscription has been cancelled.\n\n"
        f"Plan: {subscription.plan.name}\n"
        f"Cancelled at: {subscription.updated_at}\n\n"
        f"Thank you for using our service."
    )

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner_email],
            fail_silently=False,
        )
        logger.info(f"Sent cancellation notification to {owner_email}")
    except Exception as e:
        logger.error(f"Failed to send cancellation notification: {e}")


def send_invoice_receipt(invoice: Invoice) -> None:
    """
    Send invoice receipt email.

    Args:
        invoice: Paid invoice
    """
    company = invoice.company
    owner_email = company.owner.email

    subject = f"Payment Receipt - {company.name}"
    message = (
        f"Thank you for your payment!\n\n"
        f"Amount: ${invoice.amount}\n"
        f"Invoice ID: {invoice.stripe_invoice_id}\n"
        f"Paid at: {invoice.paid_at}\n\n"
        f"Invoice PDF: {invoice.invoice_pdf}\n"
    )

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner_email],
            fail_silently=False,
        )
        logger.info(f"Sent invoice receipt to {owner_email}")
    except Exception as e:
        logger.error(f"Failed to send invoice receipt: {e}")


def notify_payment_failed(invoice: Invoice) -> None:
    """
    Send notification about failed payment.

    Args:
        invoice: Invoice with failed payment
    """
    company = invoice.company
    owner_email = company.owner.email

    subject = f"Payment Failed - {company.name}"
    message = (
        f"We were unable to process your payment.\n\n"
        f"Amount: ${invoice.amount}\n"
        f"Invoice ID: {invoice.stripe_invoice_id}\n\n"
        f"Please update your payment method to continue your subscription."
    )

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [owner_email],
            fail_silently=False,
        )
        logger.info(f"Sent payment failure notification to {owner_email}")
    except Exception as e:
        logger.error(f"Failed to send payment failure notification: {e}")
